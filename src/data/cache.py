"""Cache-aside helper for the data layer (S11) — pull once, read forever.

`read_or_fetch` is the gatekeeper that guarantees each expensive online pull happens
at most once: if the Parquet already sits on disk it is read straight off disk and the
network is never touched; otherwise the adapter runs and its result is frozen to Parquet.
"""

from __future__ import annotations

import os
from collections.abc import Callable

import pandas as pd


def read_or_fetch(path: str, fetch_fn: Callable[[], pd.DataFrame]) -> pd.DataFrame:
    """Return the Parquet at `path` if it exists; else call `fetch_fn()`, write the
    result to Parquet (pyarrow), and return it. Idempotent (second call hits disk)."""
    if os.path.exists(path):
        return pd.read_parquet(path)
    df = fetch_fn()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    df.to_parquet(path, index=False)
    return df
