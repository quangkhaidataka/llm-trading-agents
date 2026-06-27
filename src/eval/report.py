# src/eval/report.py — single-file interactive explainability web report (F18, spec §9)
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

# Plotly is loaded in the BROWSER from a CDN — NOT a Python dependency.
PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.35.2.min.js"

# Tiny self-contained page template. Three holes are filled by build_report_html (via str.replace,
# so the JS/CSS braces below stay literal and readable):
#   __PLOTLY_CDN__  = the CDN URL for the Plotly <script>
#   __CHART_JSON__  = Plotly figure (data+layout) as JSON  -> Plotly.newPlot(...)
#   __TRACE_JSON__  = {date -> day-record} map embedded inline (the panel's data source)
# A plotly_click handler looks up the clicked date and writes its reasoning into #panel.
HTML_TEMPLATE = """<!doctype html><html><head><meta charset="utf-8">
<title>Agent — Decision Report</title>
<script src="__PLOTLY_CDN__"></script>
<style>body{font-family:sans-serif;margin:0}
 #chart{width:100%;height:60vh}
 #panel{padding:1em 2em;border-top:1px solid #ccc;max-width:1100px;margin:0 auto}
 #panel h2{margin:.2em 0} #panel h3{margin:.8em 0 .2em;color:#333}
 .sig{font-weight:bold} .muted{color:#666} .bull{color:#137333} .bear{color:#a50e0e}
 ul{margin:.2em 0;padding-left:1.2em}</style>
</head><body>
 <div id="chart"></div>
 <div id="panel"><em>Click any day on the curve to see why the system decided.</em></div>
 <script>
  const TRACE = __TRACE_JSON__;        // date -> full decision record (embedded inline)
  const FIG = __CHART_JSON__;
  Plotly.newPlot('chart', FIG.data, FIG.layout, {responsive:true});
  document.getElementById('chart').on('plotly_click', function(ev){
    const day = ev.points[0].x;        // clicked date (ISO string)
    document.getElementById('panel').innerHTML = renderDay(TRACE[day], day);
  });
  function esc(s){
    if(s === null || s === undefined) return '';
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }
  function renderDay(d, day){          // build the side-panel HTML from one trace record
    if(!d) return '<em>No trace for this day (' + esc(day) + ').</em>';
    const a = d.agents || {};
    const news = a.news || {}, macro = a.macro || {}, tech = a.technical || {}, mem = a.memory || {};
    const deb = d.debate || {}, dec = d.decision || {};
    let h = '<h2>' + esc(d.date) + ' — ' + esc(d.ticker || '') + '</h2>';
    h += '<p class="muted">price ' + esc(d.price) + ' · position ' + esc(d.position) +
         ' · action <span class="sig">' + esc(d.action) + '</span></p>';

    h += '<h3>Final decision</h3><p><span class="sig">new_position ' + esc(dec.new_position) +
         '</span>' + (dec.vetoed ? ' <span class="bear">(VETOED)</span>' : '') +
         '<br>conviction ' + esc(d.conviction) + '<br>' + esc(dec.reason) + '</p>';

    h += '<h3>Debate</h3>';
    h += '<p><span class="bull">Bull:</span> ' + esc(deb.bull_case) + '</p>';
    h += '<p><span class="bear">Bear:</span> ' + esc(deb.bear_case) + '</p>';
    h += '<p class="muted">thesis still valid: ' + esc(deb.thesis_still_valid) +
         ' · target_direction ' + esc(deb.target_direction) + ' · action ' + esc(deb.action) + '</p>';

    h += '<h3>Analysts</h3><ul>';
    h += '<li><b>News</b> [' + esc(news.signal) + ', conf ' + esc(news.confidence) +
         ', sent ' + esc(news.sentiment) + ']: ' + esc(news.rationale) + '</li>';
    h += '<li><b>Macro</b> [' + esc(macro.regime) + ', risk ' + esc(macro.macro_risk) +
         ']: ' + esc(macro.rationale) + '</li>';
    h += '<li><b>Technical</b> [' + esc(tech.signal) + ', conf ' + esc(tech.confidence) +
         ']: ' + esc(tech.rationale) + '</li>';
    h += '<li><b>Memory</b>: ' + esc(mem.lesson) + '</li>';
    h += '</ul>';

    const items = d.news || [];
    h += '<h3>News read (' + items.length + ')</h3><ul>';
    for(let i=0;i<items.length;i++){ h += '<li>' + esc(items[i]) + '</li>'; }
    h += '</ul>';
    return h;
  }
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
    equity = pd.read_csv(equity_csv)
    figure = _build_chart_figure(equity)
    by_date = _trace_by_date(trace_json)

    html = (
        HTML_TEMPLATE.replace("__PLOTLY_CDN__", PLOTLY_CDN)
        .replace("__CHART_JSON__", json.dumps(figure))
        .replace("__TRACE_JSON__", json.dumps(by_date))
    )
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out_path


def _build_chart_figure(equity: pd.DataFrame) -> dict:
    """Build the Plotly figure dict (data+layout) — two cumulative-PnL line traces
    (strategy vs buy & hold) sharing the date x-axis, points clickable. JSON-serializable."""
    dates = [str(d) for d in equity["date"].tolist()]
    # Prefer cum_pnl_* columns (Step-4 backtest); fall back to equity_* level columns.
    if "cum_pnl_strategy" in equity.columns:
        strat = equity["cum_pnl_strategy"].astype(float).tolist()
        bh = equity["cum_pnl_buyhold"].astype(float).tolist()
    else:
        strat = equity["equity_strategy"].astype(float).tolist()
        bh = equity["equity_buyhold"].astype(float).tolist()
    data = [
        {
            "x": dates,
            "y": strat,
            "type": "scatter",
            "mode": "lines+markers",
            "name": "Strategy",
            "marker": {"size": 4},
        },
        {
            "x": dates,
            "y": bh,
            "type": "scatter",
            "mode": "lines",
            "name": "Buy & Hold",
        },
    ]
    layout = {
        "title": "Cumulative PnL — Strategy vs Buy & Hold (click a day for the reasoning)",
        "xaxis": {"title": "Date"},
        "yaxis": {"title": "Cumulative PnL ($)"},
        "hovermode": "closest",
    }
    return {"data": data, "layout": layout}


def _trace_by_date(trace_json: str) -> dict[str, dict]:
    """Load results/trace.json and re-key the per-day records by ISO date string so the
    browser's plotly_click handler can look up the clicked day in O(1)."""
    records = json.loads(Path(trace_json).read_text(encoding="utf-8"))
    return {str(rec["date"]): rec for rec in records}
