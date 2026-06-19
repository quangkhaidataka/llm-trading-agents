"""MemoryStore — FAISS wrapper with point-in-time write/retrieve (spec §7, §12.1).

Non-parametric "learning": the LLM is frozen; behavior changes only because the
retrieved memory changes. An episode is (state -> action -> outcome).

DELAYED WRITE (mandatory anti-leak, spec §7.1): the day-t episode is `stage`d on day
t but embedded + added to FAISS only when its forward-return window closes at t+1+h
(`flush_due`). `retrieve` pulls only episodes whose outcome has closed
(outcome_closed_t <= obs.t). Writing earlier = leakage.

Reward is the AAPL-DRIFT-DEMEANED forward return (ADR-002, corrects spec §7.1):
  reward = sign(action) * (forward_return(t,h) - mu),  forward_return = P[t+1+h]/P[t+1] - 1,
  mu = AAPL's trailing average h-session return over config.reward_drift_window (<= t).
`flat` actions (sign 0) get reward 0 (accepted; memory cannot learn from good flat calls).

The FAISS IndexFlatIP (exact cosine over L2-normalized vectors) is used in BOTH modes.
Only the embedder is mode-dependent: online = sentence-transformers (config.embedding_model),
offline = a deterministic hash embedder (no torch) so make check stays light + reproducible.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from typing import Any

from config import Config
from src.data.loaders import Observation

_OFFLINE_EMBED_DIM = 64  # dim of the offline deterministic hash embedding (mock only)


@dataclass
class Episode:
    t: date
    state_text: str           # embedded text: news + market state at t (Observation.to_memory_text())
    action: int               # -1 short / 0 flat / +1 long taken at t
    reward: float | None = None        # drift-demeaned forward return; None until window closes
    outcome_closed_t: date | None = None  # = t+1+h trading day; set on flush; retrievable only then


class MemoryStore:
    """Wraps a FAISS index + Episode metadata. Append-only and strictly point-in-time."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.pending: list[Episode] = []   # staged, not yet closed
        self.closed: list[Episode] = []    # aligned 1:1 with FAISS index rows
        self.index: Any = None             # faiss.IndexFlatIP, created lazily at first add
        self._cache: dict[tuple[str, date], list[float]] = {}  # (ticker, date) -> embedding
        self._model: Any = None            # lazily-loaded sentence-transformers model (online)

    def stage(self, obs: Observation, action: int) -> None:
        """Record a pending Episode for day t (reward=None). NOT embedded or searchable until
        its window closes at t+1+h — this is the delayed write."""
        self.pending.append(
            Episode(t=obs.t, state_text=obs.to_memory_text(), action=action)
        )

    def flush_due(self, current_t: date, price_series) -> None:
        """Close every pending episode whose t+1+h trading day exists and is <= current_t:
        compute its drift-demeaned reward, embed it, and add it to the FAISS index."""
        import pandas as pd

        idx = price_series.index
        still_pending: list[Episode] = []
        for ep in self.pending:
            ts = pd.Timestamp(ep.t)
            if ts not in idx:
                still_pending.append(ep)
                continue
            exit_pos = idx.get_loc(ts) + 1 + self.config.h
            if exit_pos < len(idx) and idx[exit_pos].date() <= current_t:
                ep.reward = self._reward(ep.action, price_series, ep.t, self.config)
                ep.outcome_closed_t = idx[exit_pos].date()
                self._add(ep)
            else:
                still_pending.append(ep)
        self.pending = still_pending

    def retrieve(self, obs: Observation, k: int) -> list[Episode]:
        """Return the k most similar CLOSED episodes (outcome_closed_t <= obs.t). Empty on cold start."""
        import numpy as np

        if self.index is None or self.index.ntotal == 0:
            return []
        q = np.asarray(self._embed(obs.to_memory_text(), (obs.ticker, obs.t)), dtype="float32")
        _, indices = self.index.search(q[None, :], min(k, self.index.ntotal))
        out: list[Episode] = []
        for i in indices[0]:
            if i == -1:
                continue
            ep = self.closed[i]
            if ep.outcome_closed_t is not None and ep.outcome_closed_t <= obs.t:
                out.append(ep)
        return out[:k]

    def _add(self, ep: Episode) -> None:
        """Embed a closed episode and append it to the FAISS index + metadata list."""
        import faiss
        import numpy as np

        vec = np.asarray(
            self._embed(ep.state_text, (self.config.ticker, ep.t)), dtype="float32"
        )
        if self.index is None:
            self.index = faiss.IndexFlatIP(len(vec))
        self.index.add(vec[None, :])
        self.closed.append(ep)

    def _embed(self, text: str, cache_key: tuple[str, date]) -> list[float]:
        """Text -> L2-normalized 'meaning coordinates'; cached by (ticker, date) so a day's
        embedding is computed once. Online = pinned sentence-transformers; offline = hash embedder."""
        if cache_key in self._cache:
            return self._cache[cache_key]
        if self.config.offline:
            vec = self._hash_embed(text)
        else:
            if self._model is None:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.config.embedding_model)
            vec = self._model.encode([text], normalize_embeddings=True)[0].tolist()
        self._cache[cache_key] = vec
        return vec

    @staticmethod
    def _hash_embed(text: str) -> list[float]:
        """Deterministic, dependency-free bag-of-hashed-tokens embedding (offline mock only).
        Uses md5 (NOT Python's salted hash()) so the same text maps to the same vector across runs."""
        import numpy as np

        vec = np.zeros(_OFFLINE_EMBED_DIM, dtype="float32")
        for tok in text.lower().split():
            bucket = int(hashlib.md5(tok.encode()).hexdigest(), 16) % _OFFLINE_EMBED_DIM
            vec[bucket] += 1.0
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        return vec.tolist()

    @staticmethod
    def _reward(action: int, price_series, t: date, config: Config) -> float:
        """sign(action) * (forward_return(t,h) - mu); forward_return = P[t+1+h]/P[t+1] - 1;
        mu = trailing AAPL drift (mean h-session return over config.reward_drift_window, <= t)
        when config.reward_benchmark == 'aapl_drift', else 0 (raw). Point-in-time: mu uses only
        closes <= t; forward_return uses the now-closed window."""
        import pandas as pd

        close = price_series["close"]
        pos = price_series.index.get_loc(pd.Timestamp(t))
        forward_return = float(close.iloc[pos + 1 + config.h]) / float(close.iloc[pos + 1]) - 1.0

        mu = 0.0
        if config.reward_benchmark == "aapl_drift":
            past = close.values[: pos + 1].astype(float)  # closes <= t only
            h = config.h
            if len(past) > h:
                h_returns = past[h:] / past[:-h] - 1.0
                window = h_returns[-config.reward_drift_window :]
                if len(window):
                    mu = float(window.mean())

        sign = (action > 0) - (action < 0)  # -1 / 0 / +1
        return float(sign * (forward_return - mu))
