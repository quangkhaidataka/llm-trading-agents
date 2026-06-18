# S6.1 — Interactive Explainability Web Report (`results/report.html`)

## Objective
This is where months of plumbing finally *speak*. A reviewer should not have to
read our code to believe the system reasons — they should be able to open a single
web page, see the strategy's cumulative PnL climb (or stumble) against plain buy &
hold AAPL, and then, on a hunch, **click the day of a big jump or a sharp drop** and
immediately read *why the system did what it did that day*. A side panel slides in:
the news it actually read, what each analyst concluded and in one breath why
(News/Macro/Technical/Memory), the Bull case, the Bear case, whether the entry
thesis still held, the conviction number, and the final call with its reason. This is
the concrete payoff of the project's explainability claim (spec §9): the A2A protocol
made *visible*, one day at a time. We keep it deliberately plain — one chart, one
panel — because the point is the reasoning, not the styling. And crucially it is a
**single self-contained `.html` file**: no server, no build step, no new Python
dependency. The chart library (Plotly) loads from a CDN; the entire decision trace is
embedded inline as JSON so the file works opened straight off disk (double-click) and
can even be committed as a sample artifact. This is feature **F18**.

## Inputs and Outputs
- **Inputs:**
  - `results/equity_curve.csv` — per-date strategy equity and the buy & hold AAPL
    reference line (from Step 4's backtest; both start at \$1M). Columns include
    `date, equity_strategy, equity_buyhold` (or `cum_pnl_*`); read for the chart.
  - `results/trace.json` — the structured per-day decision trace produced by the
    Step-4 `commit` node: one record per date with `cum_pnl_strategy`,
    `cum_pnl_buyhold`, `position`, `action`, `conviction` (+ breakdown), the `news`
    read, each agent's `{signal/regime, rationale}` (News/Macro/Technical/Memory),
    the debate `{bull_case, bear_case, thesis_still_valid}`, and the final
    `{new_position, reason}`. This is the panel's data.
  - `out_path: str` — where to write the page (default `results/report.html`).
- **Outputs:**
  - **`results/report.html`** — one self-contained interactive HTML file (gitignored
    under `results/`, but committable as a sample): a cumulative-PnL line chart
    (strategy vs buy & hold) with clickable daily points + a side `<div>` panel that
    renders the clicked day's trace. Plotly via CDN; trace JSON embedded inline.
  - No new entry in `requirements.txt` (CDN-loaded JS, stdlib-only Python).

## Skeleton Python Code
```python
# src/eval/report.py — single-file interactive explainability web report (F18, spec §9)
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

# Plotly is loaded in the BROWSER from a CDN — NOT a Python dependency.
PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.35.2.min.js"

# Tiny self-contained page template. Two data holes are filled by build_report_html:
#   {chart_json}  = Plotly figure (data+layout) as JSON  -> Plotly.newPlot(...)
#   {trace_json}  = {date -> day-record} map embedded inline (the panel's data source)
# A plotly_click handler looks up the clicked date and writes its reasoning into #panel.
HTML_TEMPLATE = """<!doctype html><html><head><meta charset="utf-8">
<title>AAPL Agent — Decision Report</title>
<script src="{plotly_cdn}"></script>
<style>body{{font-family:sans-serif;margin:0;display:flex}}
 #chart{{flex:2}} #panel{{flex:1;padding:1em;border-left:1px solid #ccc;overflow:auto;height:100vh}}</style>
</head><body>
 <div id="chart"></div>
 <div id="panel"><em>Click any day on the curve to see why the system decided.</em></div>
 <script>
  const TRACE = {trace_json};          // date -> full decision record (embedded inline)
  Plotly.newPlot('chart', {chart_json}.data, {chart_json}.layout);
  document.getElementById('chart').on('plotly_click', function(ev){{
    const day = ev.points[0].x;        // clicked date
    document.getElementById('panel').innerHTML = renderDay(TRACE[day]);
  }});
  function renderDay(d){{               // build the side-panel HTML from one trace record
    if(!d) return '<em>No trace for this day.</em>';
    /* news read · each agent signal+rationale · bull/bear/thesis · conviction · final call+reason */
    return '...';
  }}
 </script>
</body></html>"""


def build_report_html(equity_csv: str, trace_json: str, out_path: str = "results/report.html") -> str:
    """Build ONE self-contained interactive HTML report and write it to out_path.

    Reads the equity curve (strategy vs buy & hold) + the per-day decision trace,
    builds a Plotly cumulative-PnL figure with clickable daily points, embeds the
    trace JSON inline, and fills HTML_TEMPLATE. Plotly is loaded from a CDN, the trace
    is embedded inline, so the file needs no server and no new Python dependency — it
    opens straight from disk and powers the click-to-explain panel (spec §9). Returns out_path.
    """
    ...


def _build_chart_figure(equity: pd.DataFrame) -> dict:
    """Build the Plotly figure dict (data+layout) — two cumulative-PnL line traces
    (strategy vs buy & hold) sharing the date x-axis, points clickable. JSON-serializable."""
    ...


def _trace_by_date(trace_json: str) -> dict[str, dict]:
    """Load results/trace.json and re-key the per-day records by ISO date string so the
    browser's plotly_click handler can look up the clicked day in O(1)."""
    ...
```

## How It Connects
The story runs straight through from the backtest to the browser. During Step 4 the
graph's `commit` node already wrote, for every trading day, both the running PnL (so
the curve can be drawn) and the full human-readable reasoning for that day into
`results/trace.json`, while the dollar equity of the strategy and of buy & hold went
into `results/equity_curve.csv`. `build_report_html` is the small bridge that fuses
the two: it draws the equity CSV as a two-line cumulative-PnL chart with Plotly, then
embeds the entire trace JSON *inside* the same HTML file and wires a one-line click
handler so that clicking a day looks that date up in the embedded map and paints its
reasoning — news, each analyst, the bull/bear debate, the conviction, the final
decision — into a side panel. Because the chart library comes from a CDN and the data
is inlined, the result is one portable file a reviewer double-clicks to open; the
notebook (S6.3) merely links to it, and the README points at it as the headline
demonstration that the system is not a black box.

## Key Technology, Design Patterns & Packages
- **Plotly via CDN (`<script src=...plot.ly...>`)** — interactive, zoomable chart with
  a built-in `plotly_click` event, the simplest path to clickable points; loaded in the
  browser so it adds **zero** Python dependency and needs no build tooling.
- **Inline JSON embedding (`json.dumps` into a template string)** — the whole trace
  travels inside the HTML, so the page is self-contained and works opened from disk;
  no server, no `fetch`, no CORS.
- **Python stdlib + pandas only** — `pathlib`/`json` plus a `pandas` read of the
  equity CSV we already produce; nothing new installed.
- **Template-string generator (no web framework)** — one constant `HTML_TEMPLATE`
  with two data holes; deliberately no Flask/Dash/Jinja — YAGNI, and a static file is
  more portable and committable than a running server.
- **Deliberately minimal UI (one chart + one panel)** — explainability is the
  deliverable, not styling; keeps the file small, reviewable, and robust.

## Definition of Done

- [ ] **Acceptance command:** `.venv/bin/python -c "from src.eval.report import build_report_html; build_report_html('results/equity_curve.csv','results/trace.json')"` writes `results/report.html`; double-click / `open results/report.html` opens with no server.
- [ ] **Tests:** offline & deterministic (`Config(offline=True)`, fixtures only) — a test asserts `build_report_html` returns a single self-contained HTML file that embeds the trace JSON inline and references the Plotly CDN (`cdn.plot.ly`), with **no server, no `fetch`, and no new Python dependency** (stdlib + pandas only).
- [ ] **Gate:** `make check` green (lint + typecheck + test + e2e).
- [ ] **features.json:** add **F18** (interactive explainable report) and flip it to `passing` with evidence (acceptance command + the offline test) once verified.
- [ ] **Artifacts:** `results/report.html` — one self-contained file: a clickable cumulative-PnL line chart (strategy vs buy & hold) where clicking a day shows that day's news read, per-agent signal + rationale (News/Macro/Technical/Memory), the bull/bear/thesis debate, the conviction, and the final decision + reason.
- [ ] **Rules:** the report **reads `results/trace.json` + `results/equity_curve.csv` only — never recomputes**; no new `requirements.txt` entry (Plotly via CDN, stdlib-only Python); no Flask/Dash/Jinja/server (YAGNI).
- [ ] **Tracking:** `PROGRESS.md` updated; run the `update-progress` + `feature-status` skills (add F18 to `features.json`); record any non-obvious choice in `DECISIONS.md`.
