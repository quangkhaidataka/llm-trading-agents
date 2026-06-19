"""LangGraph orchestration (spec §4.2, §12.2) — the per-day state machine.

Within a day the typed GraphState flows downhill:
  observe -> [news, macro, technical, memory]  (parallel fan-out)
          -> debate (state-aware Bull/Bear)    -> ResearchStance
          -> conviction (computed z, §7.3)      -> calibrated number
          -> position_manager (veto + hysteresis) -> TradeDecision
          -> commit (apply + write per-day trace)

Across days, `run_one_day` carries PortfolioState and drives the memory's stage/flush
rhythm: stage(t) after the decision, flush_due(t) to close + index any episode whose
t+1+h window has elapsed (delayed write, point-in-time). The commit node writes a full
per-day decision trace to config.log_dir — the source the Step-6 web report reads.

Conviction note: the number passed to the PositionManager is the RAW score z (composite +
self-consistency). The Step-5 isotonic/Platt calibrator (Layer 3) will map z -> P(correct)
in front of the PositionManager; until then z is used directly.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, TypedDict

from config import Config
from src.agents.debate import DebateAgent
from src.agents.macro import MacroAgent
from src.agents.memory import MemoryAgent
from src.agents.news import NewsAgent
from src.agents.position_manager import PositionManager
from src.agents.technical import TechnicalAgent
from src.data.loaders import Observation
from src.eval.calibration import (
    composite_conviction,
    raw_conviction,
    self_consistency_conviction,
)
from src.memory.store import MemoryStore
from src.schemas import (
    MacroSignal,
    MemoryContext,
    NewsSignal,
    PortfolioState,
    ResearchStance,
    TechnicalSignal,
    TradeDecision,
)

_DIR = {"long": 1, "flat": 0, "short": -1}


class GraphState(TypedDict):
    """The shared, typed 'whiteboard' threaded through one day's nodes (kept minimal)."""

    obs: Observation
    portfolio: PortfolioState
    news: NewsSignal
    macro: MacroSignal
    technical: TechnicalSignal
    memory: MemoryContext
    stance: ResearchStance
    conviction: float
    decision: TradeDecision


def build_graph(config: Config, store: MemoryStore):
    """Wire and compile the per-day graph. Returns the compiled LangGraph app.

    Topology is fixed (observe -> 4 analysts -> debate -> conviction -> position_manager
    -> commit); the ablation flags change what individual nodes PRODUCE rather than forking
    the graph (use_macro/use_memory/use_debate)."""
    from langgraph.graph import END, START, StateGraph

    news_agent = NewsAgent(config)
    macro_agent = MacroAgent(config)
    technical_agent = TechnicalAgent(config)
    memory_agent = MemoryAgent(config, store)
    debate_agent = DebateAgent(config)
    manager = PositionManager(config)

    def observe(state: GraphState) -> dict:
        return {}  # fan-out anchor; the Observation is seeded by run_one_day

    def news_node(state: GraphState) -> dict:
        return {"news": news_agent.run(state["obs"], state["portfolio"])}

    def macro_node(state: GraphState) -> dict:
        if not config.use_macro:
            return {"macro": MacroSignal(
                rationale="(macro disabled)", regime="neutral", macro_risk=0.0, drivers=[]
            )}
        return {"macro": macro_agent.run(state["obs"], state["portfolio"])}

    def technical_node(state: GraphState) -> dict:
        return {"technical": technical_agent.run(state["obs"], state["portfolio"])}

    def memory_node(state: GraphState) -> dict:
        if not config.use_memory:
            return {"memory": MemoryContext(analogs=[], lesson="(memory disabled)")}
        return {"memory": memory_agent.run(state["obs"], state["portfolio"])}

    def debate_node(state: GraphState) -> dict:
        if not config.use_debate:
            return {"stance": _fallback_stance(state["news"], state["technical"])}
        return {"stance": debate_agent.run(
            state["obs"], state["portfolio"],
            state["news"], state["macro"], state["technical"], state["memory"],
        )}

    def conviction_node(state: GraphState) -> dict:
        news, technical = state["news"], state["technical"]
        signals = [
            {"direction": _DIR[news.signal], "confidence": news.confidence},
            {"direction": _DIR[technical.signal], "confidence": technical.confidence},
        ]
        memory_consistency = _memory_consistency(config, store, state["obs"])
        z_raw = composite_conviction(signals, memory_consistency, config)
        if config.use_debate:
            actions = debate_agent.sample(
                state["obs"], state["portfolio"],
                news, state["macro"], technical, state["memory"], config.K,
            )
            z_sc = self_consistency_conviction(actions, config.K)
            z = raw_conviction(z_raw, z_sc, config)
        else:
            z = z_raw
        return {"conviction": z}

    def position_manager_node(state: GraphState) -> dict:
        obs = state["obs"]
        vol = obs.indicators.get("vol20")
        realized_vol = float(vol) if vol is not None and vol == vol else 0.0  # NaN -> 0
        decision = manager.decide(
            obs, state["portfolio"], state["stance"], state["macro"],
            conviction=state["conviction"],
            realized_vol=realized_vol,
            drawdown=0.0,  # equity-curve drawdown is wired by the backtest (S4)
            disagreement=_disagreement(state["news"], state["technical"]),
        )
        return {"decision": decision}

    def commit_node(state: GraphState) -> dict:
        new_portfolio = _apply(state["portfolio"], state["decision"], state["obs"])
        _write_trace(config, state)
        return {"portfolio": new_portfolio}

    graph = StateGraph(GraphState)
    for name, fn in [
        ("observe", observe), ("news", news_node), ("macro", macro_node),
        ("technical", technical_node), ("memory", memory_node), ("debate", debate_node),
        ("conviction", conviction_node), ("position_manager", position_manager_node),
        ("commit", commit_node),
    ]:
        graph.add_node(name, fn)

    graph.add_edge(START, "observe")
    for analyst in ("news", "macro", "technical", "memory"):
        graph.add_edge("observe", analyst)   # fan out
        graph.add_edge(analyst, "debate")    # join on all four
    graph.add_edge("debate", "conviction")
    graph.add_edge("conviction", "position_manager")
    graph.add_edge("position_manager", "commit")
    graph.add_edge("commit", END)
    return graph.compile()


def run_one_day(app, t: date, portfolio: PortfolioState, store: MemoryStore) -> TradeDecision:
    """Run the graph for day t, carry PortfolioState across days, and drive the memory
    stage/flush rhythm. Mutates `portfolio` in place for t+1; returns the day's TradeDecision."""
    from src.data.loaders import get_observation, load_prices

    config = store.config
    obs = get_observation(config.ticker, t)
    state_in = PortfolioState() if config.stateless else portfolio  # stateless = daily classifier
    result = app.invoke({"obs": obs, "portfolio": state_in})
    decision: TradeDecision = result["decision"]

    if not config.stateless:
        new = result["portfolio"]
        portfolio.current_position = new.current_position
        portfolio.active_thesis = new.active_thesis
        portfolio.entry_price = new.entry_price
        portfolio.days_held = new.days_held

    # delayed-write memory rhythm: record today, then close any episode whose window elapsed
    store.stage(obs, decision.new_position)
    store.flush_due(t, load_prices(config.ticker, t))
    return decision


# ── helpers ──────────────────────────────────────────────────────────────────
def _apply(old: PortfolioState, decision: TradeDecision, obs: Observation) -> PortfolioState:
    """Fold a TradeDecision into the next PortfolioState (entry/thesis/days_held)."""
    pos = decision.new_position
    if pos == 0:  # flat / closed / vetoed
        return PortfolioState(current_position=0, active_thesis="", entry_price=None, days_held=0)
    if pos == old.current_position:  # maintained
        return PortfolioState(
            current_position=pos, active_thesis=decision.new_thesis,
            entry_price=old.entry_price, days_held=old.days_held + 1,
        )
    return PortfolioState(  # opened or flipped
        current_position=pos, active_thesis=decision.new_thesis,
        entry_price=obs.price, days_held=1,
    )


def _fallback_stance(news: NewsSignal, technical: TechnicalSignal) -> ResearchStance:
    """Deterministic stance from signal aggregation (no-debate ablation, use_debate=False)."""
    score = _DIR[news.signal] * news.confidence + _DIR[technical.signal] * technical.confidence
    target: Literal[-1, 0, 1] = 1 if score > 0 else -1 if score < 0 else 0
    action: Literal["hold", "open", "close", "flip"] = "open" if target != 0 else "hold"
    return ResearchStance(
        bull_case="(no-debate ablation: signal aggregation)",
        bear_case="(no-debate ablation: signal aggregation)",
        thesis_still_valid=True,
        action=action,
        target_direction=target,
        conviction=min(1.0, abs(score)),
    )


def _memory_consistency(config: Config, store: MemoryStore, obs: Observation) -> float:
    """Share of retrieved closed analogs whose action paid off (reward > 0); 0.5 if none."""
    if not config.use_memory:
        return 0.5
    episodes = store.retrieve(obs, config.k)
    if not episodes:
        return 0.5
    return sum(1 for e in episodes if (e.reward or 0.0) > 0) / len(episodes)


def _disagreement(news: NewsSignal, technical: TechnicalSignal) -> float:
    """Directional disagreement among the non-flat analyst votes (1 = opposed, 0 = aligned/flat)."""
    dirs = [d for d in (_DIR[news.signal], _DIR[technical.signal]) if d != 0]
    if not dirs:
        return 0.0
    return 1.0 - abs(sum(dirs) / len(dirs))


def _write_trace(config: Config, state: GraphState) -> None:
    """Append-only per-day decision trace -> config.log_dir/{ticker}_{t}.json (Step-6 report source)."""
    import json
    import os

    obs = state["obs"]
    os.makedirs(config.log_dir, exist_ok=True)
    record = {
        "date": obs.t.isoformat(),
        "ticker": obs.ticker,
        "price": obs.price,
        "news": [it.get("title") for it in obs.aapl_news[: config.max_news_per_day]],
        "agents": {
            "news": state["news"].model_dump(),
            "macro": state["macro"].model_dump(),
            "technical": state["technical"].model_dump(),
            "memory": state["memory"].model_dump(),
        },
        "debate": {
            "bull_case": state["stance"].bull_case,
            "bear_case": state["stance"].bear_case,
            "thesis_still_valid": state["stance"].thesis_still_valid,
            "action": state["stance"].action,
        },
        "conviction": state["conviction"],
        "decision": state["decision"].model_dump(),
    }
    path = os.path.join(config.log_dir, f"{config.ticker}_{obs.t.isoformat()}.json")
    with open(path, "w") as fh:
        json.dump(record, fh, indent=2)
