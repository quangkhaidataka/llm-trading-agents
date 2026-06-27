"""S6.1 tests — the interactive explainability web report (F18), offline & deterministic.

No network, no server, no real LLM: build_report_html reads a tiny equity CSV + trace JSON written
to a tmp dir and produces ONE self-contained HTML file. The asserts encode the DoD: Plotly via CDN,
trace embedded inline, no `fetch`, no server, stdlib + pandas only.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.eval.report import (
    PLOTLY_CDN,
    _build_chart_figure,
    _trace_by_date,
    build_report_html,
)

EQUITY_CSV = (
    "date,position,action,P,shares,pnl,fee,equity,cum_pnl_strategy,cum_pnl_buyhold\n"
    "2025-01-02,0,hold,242.30,0.0,0.0,0.0,1000000.0,0.0,0.0\n"
    "2025-01-03,1,open,241.81,4135.0,0.0,100.0,999900.0,-100.0,-2009.5\n"
    "2025-01-06,1,hold,244.00,4135.0,9000.0,0.0,1008900.0,8900.0,5050.0\n"
)

TRACE = [
    {
        "date": "2025-01-02",
        "ticker": "AAPL",
        "price": 242.30,
        "news": ["Apple unveils new chip", "Analyst upgrade for AAPL"],
        "agents": {
            "news": {"rationale": "Upbeat coverage <with> & ampersand", "sentiment": 0.2,
                     "signal": "long", "confidence": 0.7},
            "macro": {"rationale": "Mixed backdrop", "regime": "neutral", "macro_risk": 0.4,
                      "drivers": ["Fed/rates"]},
            "technical": {"rationale": "RSI neutral", "signal": "flat", "confidence": 0.5,
                          "indicators": {"RSI": 46.0}},
            "memory": {"analogs": [], "lesson": "No precedent"},
        },
        "debate": {"bull_case": "Strong product cycle", "bear_case": "Lawsuit risk",
                   "thesis_still_valid": False, "action": "open", "target_direction": 1},
        "conviction": 0.46,
        "decision": {"new_position": 1, "new_thesis": "long thesis", "vetoed": False,
                     "reason": "open long (conviction 0.46 >= tau_enter 0.45)"},
        "position": 0,
        "action": "hold",
        "cum_pnl_strategy": 0.0,
        "cum_pnl_buyhold": 0.0,
    },
    {
        "date": "2025-01-03",
        "ticker": "AAPL",
        "price": 241.81,
        "news": [],
        "agents": {
            "news": {"rationale": "No news", "sentiment": 0.0, "signal": "flat", "confidence": 0.5},
            "macro": {"rationale": "Quiet", "regime": "neutral", "macro_risk": 0.3, "drivers": []},
            "technical": {"rationale": "Flat", "signal": "flat", "confidence": 0.5, "indicators": {}},
            "memory": {"analogs": [], "lesson": "No precedent"},
        },
        "debate": {"bull_case": "", "bear_case": "", "thesis_still_valid": True,
                   "action": "hold", "target_direction": 0},
        "conviction": 0.5,
        "decision": {"new_position": 1, "new_thesis": "long thesis", "vetoed": False,
                     "reason": "hold"},
        "position": 1,
        "action": "open",
        "cum_pnl_strategy": -100.0,
        "cum_pnl_buyhold": -2009.5,
    },
]


def _write_inputs(tmp_path: Path) -> tuple[str, str]:
    eq = tmp_path / "equity_curve.csv"
    tr = tmp_path / "trace.json"
    eq.write_text(EQUITY_CSV, encoding="utf-8")
    tr.write_text(json.dumps(TRACE), encoding="utf-8")
    return str(eq), str(tr)


def test_build_report_writes_self_contained_html(tmp_path: Path) -> None:
    eq, tr = _write_inputs(tmp_path)
    out = tmp_path / "report.html"
    ret = build_report_html(eq, tr, str(out))

    assert ret == str(out)
    assert out.exists()
    html = out.read_text(encoding="utf-8")

    # One self-contained HTML document.
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert html.rstrip().endswith("</html>")

    # Plotly via CDN — the only external resource; loaded in the browser (no Python dep).
    assert PLOTLY_CDN in html
    assert "cdn.plot.ly" in html
    assert "Plotly.newPlot" in html

    # No server / no remote data fetch — the page works opened straight off disk.
    assert "fetch(" not in html
    assert "<form" not in html

    # No web framework / server stack leaked into the artifact.
    low = html.lower()
    assert "flask" not in low and "dash" not in low and "jinja" not in low


def test_trace_embedded_inline_and_clickable(tmp_path: Path) -> None:
    eq, tr = _write_inputs(tmp_path)
    out = tmp_path / "report.html"
    build_report_html(eq, tr, str(out))
    html = out.read_text(encoding="utf-8")

    # The whole decision trace travels INSIDE the HTML (no external JSON file).
    assert "Strong product cycle" in html  # bull_case
    assert "Lawsuit risk" in html  # bear_case
    assert "Apple unveils new chip" in html  # a news headline read
    assert "open long (conviction 0.46 >= tau_enter 0.45)" in html  # final reason
    assert '"2025-01-02"' in html and '"2025-01-03"' in html  # keyed by date

    # A click handler wires a clicked day to the side panel.
    assert "plotly_click" in html
    assert "renderDay" in html


def test_chart_figure_has_two_cumpnl_traces() -> None:
    import pandas as pd

    df = pd.read_csv(__import__("io").StringIO(EQUITY_CSV))
    fig = _build_chart_figure(df)
    assert set(fig) == {"data", "layout"}
    names = [t["name"] for t in fig["data"]]
    assert names == ["Strategy", "Buy & Hold"]
    # JSON-serializable (no numpy types leak through).
    json.dumps(fig)
    # Strategy markers are clickable (mode includes markers).
    assert "markers" in fig["data"][0]["mode"]


def test_trace_by_date_rekeys_by_iso_date(tmp_path: Path) -> None:
    _, tr = _write_inputs(tmp_path)
    by_date = _trace_by_date(tr)
    assert set(by_date) == {"2025-01-02", "2025-01-03"}
    assert by_date["2025-01-02"]["decision"]["new_position"] == 1
