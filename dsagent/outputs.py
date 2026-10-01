"""
Turns findings.json + a data cube into the two deliverables.

Deliberately deterministic. The model produces structured findings and a compact
cube; this file renders them. If the model wrote the HTML directly you would get
a different layout every run and occasionally a broken one.

The dashboard is one self-contained file: CSS and JS are inlined and the data is
embedded as JSON, so it works offline and can be emailed as a single attachment.
Every number in it is recomputed in the browser from the cube whenever a filter
or slider moves -- nothing is a pre-rendered picture.
"""

from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path

ASSETS = Path(__file__).parent


# --------------------------------------------------------------------------
# Data cube
# --------------------------------------------------------------------------

def build_cube(df, risk, *, id_col: str, plan_col: str, region_col: str,
               contract_col: str, mrr_col: str, dormancy_col: str,
               target_col: str, drivers: list) -> dict:
    """
    Compact, browser-friendly export of the rows the dashboard filters over.

    Categoricals become integer indices and floats are rounded, which keeps a
    9,000-row cube near 300 KB instead of several megabytes.
    """
    # Alphabetical order would put "business" before "starter", which reads as
    # noise. Rank plan tiers by their median revenue, and use the natural
    # commitment order for contracts when the labels are recognisable.
    plans = (df.groupby(plan_col)[mrr_col].median()
               .sort_values().index.astype(str).tolist())
    regions = sorted(df[region_col].dropna().astype(str).unique().tolist())
    PREFERRED = ["monthly", "quarterly", "annual", "multi-year"]
    found = df[contract_col].dropna().astype(str).unique().tolist()
    contracts = ([c for c in PREFERRED if c in found]
                 + sorted(c for c in found if c not in PREFERRED))
    pi = {v: i for i, v in enumerate(plans)}
    ri = {v: i for i, v in enumerate(regions)}
    ci = {v: i for i, v in enumerate(contracts)}

    rows = [
        [i, pi[p], ri[r], ci[c], round(float(m), 2), int(d), int(t), round(float(k), 4)]
        for i, (p, r, c, m, d, t, k) in enumerate(zip(
            df[plan_col].astype(str), df[region_col].astype(str),
            df[contract_col].astype(str), df[mrr_col],
            df[dormancy_col], df[target_col], risk))
    ]

    return {
        "columns": ["id", "plan", "region", "contract", "mrr", "dorm", "churned", "risk"],
        "plans": plans, "regions": regions, "contracts": contracts,
        "ids": df[id_col].astype(str).tolist(),
        "rows": rows,
        "drivers": [[n, round(float(v), 5)] for n, v in drivers],
    }


# --------------------------------------------------------------------------
# Markdown report
# --------------------------------------------------------------------------

def write_report(findings: dict, meta: dict, out_path: Path) -> Path:
    f = findings
    L: list[str] = []
    L.append(f"# {f.get('headline', 'Analysis')}\n")
    L.append(f"*{meta.get('question', '')}*\n")
    L.append(f"Generated {date.today().isoformat()} · source `{meta.get('csv','')}` · "
             f"reviewer verdict **{meta.get('verdict','n/a')}**\n")

    if f.get("kpis"):
        L.append("\n## Headline numbers\n")
        L.append("| Measure | Value | Context |")
        L.append("| --- | --- | --- |")
        for k in f["kpis"]:
            L.append(f"| {k.get('label','')} | {k.get('value','')} | {k.get('context','')} |")

    L.append("\n## Findings\n")
    for item in f.get("findings", []):
        L.append(f"### {item.get('title','Finding')}\n")
        L.append(item.get("detail", "") + "\n")
        if item.get("evidence"):
            L.append(f"> Evidence: {item['evidence']}\n")
        if item.get("figure"):
            L.append(f"![{item.get('title','figure')}]({item['figure']})\n")

    m = f.get("model") or {}
    if m:
        L.append("\n## Model\n")
        L.append(f"- Task: {m.get('task','')}")
        L.append(f"- {m.get('metric','metric')}: **{m.get('value','')}** "
                 f"against a baseline of {m.get('baseline','')}")
        L.append(f"- Beats baseline: {'yes' if m.get('beats_baseline') else 'no'}")
        if m.get("excluded_features"):
            L.append(f"- Excluded to prevent leakage: {', '.join(m['excluded_features'])}")

    if f.get("caveats"):
        L.append("\n## Read this before acting\n")
        L.extend(f"- {c}" for c in f["caveats"])

    if f.get("recommendations"):
        L.append("\n## Recommended actions\n")
        L.extend(f"{i}. {r}" for i, r in enumerate(f["recommendations"], 1))

    if meta.get("judge_reasons"):
        L.append("\n## Reviewer notes\n")
        L.extend(f"- {r}" for r in meta["judge_reasons"])

    out_path.write_text("\n".join(L))
    return out_path


# --------------------------------------------------------------------------
# Interactive dashboard
# --------------------------------------------------------------------------

def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


SHELL = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>__CSS__</style></head>
<body><div class="wrap">

<header>
  <div class="who">__HEADER__</div>
  <div class="meta">__META__</div>
</header>

<h1>__HEADLINE__</h1>
<p class="sub">__QUESTION__</p>
<p class="scope">Showing <span id="scope"></span> ·
  <button class="resetbtn" id="reset" type="button">reset filters</button></p>

<div id="filters"></div>
<div id="kpis"></div>

<div id="empty" hidden>No accounts match this combination of filters.</div>

<div id="sim">
  <div class="head">
    <h2>Who would this week's outreach list contain?</h2>
    <p>Set the two thresholds a customer-success team would actually operate on,
       and see how large the resulting list is, how much of the churn it catches,
       and how much of it is wasted effort.</p>
  </div>
  <div class="sliders">
    <div class="slider">
      <div class="top"><label for="dorm">Flag accounts quiet for at least</label>
        <b id="dorm-out">14 days</b></div>
      <input type="range" id="dorm" min="0" max="90" step="1" value="14">
    </div>
    <div class="slider">
      <div class="top"><label for="risk">and with a model risk score above</label>
        <b id="risk-out">30%</b></div>
      <input type="range" id="risk" min="0" max="95" step="1" value="30">
    </div>
  </div>
  <div id="sim-out"></div>
</div>

<div id="grid">
  <div class="panel">
    <h3>Churn rate by plan</h3>
    <p class="note">Account counts in brackets. Bars turn red above 15%.</p>
    <div class="chart" id="c-plan"></div>
  </div>
  <div class="panel">
    <h3>Churn rate by days since last login</h3>
    <p class="note">Hover a point for the number of accounts in that bucket.</p>
    <div class="chart" id="c-dorm"></div>
  </div>
  <div class="panel full">
    <h3>What the model relies on</h3>
    <p class="note">Permutation importance on the held-out set: how far AUC falls
      when a column is shuffled. Model-level, so it does not respond to the filters.</p>
    <div class="chart" id="c-drivers"></div>
  </div>
</div>

<div id="tablewrap">
  <div class="head"><h3>Highest-risk accounts in the current selection</h3>
    <p class="note">Top 12 by model risk score.</p></div>
  <table id="table"></table>
</div>

__FINDINGS__
__MODELPANEL__
__BOTTOM__

<footer>__FOOTER__</footer>
</div>
<script>const CUBE = __CUBE__;</script>
<script>__JS__</script>
</body></html>"""


def write_dashboard(findings: dict, meta: dict, cube: dict, out_path: Path) -> Path:
    f = findings
    m = f.get("model") or {}

    findings_html = "".join(
        f'<section class="finding"><h2>{_e(i.get("title"))}</h2>'
        f'<p>{_e(i.get("detail"))}</p>'
        + (f'<p class="evidence">{_e(i["evidence"])}</p>' if i.get("evidence") else "")
        + "</section>"
        for i in f.get("findings", [])
    )
    if findings_html:
        findings_html = ('<h2 style="font-size:19px;font-weight:500;margin:46px 0 0">'
                         "What the analysis found</h2>" + findings_html)

    model_panel = ""
    if m:
        ok = bool(m.get("beats_baseline"))
        model_panel = f"""<div class="modelband">
  <div class="kpi"><span class="v">{_e(m.get('value'))}</span>
    <div class="l">{_e(m.get('metric','Metric'))}</div>
    <div class="c">{'beats' if ok else 'does not beat'} the baseline of
      {_e(m.get('baseline'))}</div></div>
  <div class="kpi"><span class="v small">{_e(m.get('task'))}</span>
    <div class="l">Task</div><div class="c">what the model was fit to do</div></div>
  <div class="kpi"><span class="v small">
      {_e(', '.join(m.get('excluded_features') or []) or 'none')}</span>
    <div class="l">Dropped before fitting</div>
    <div class="c">columns excluded to prevent leakage</div></div>
</div>"""

    caveats = "".join(f"<li>{_e(c)}</li>" for c in f.get("caveats", []))
    recs = "".join(f"<li>{_e(r)}</li>" for r in f.get("recommendations", []))
    bottom = ""
    if caveats or recs:
        bottom = f"""<div class="cols">
  <div><h3>Read this before acting</h3>
    <div class="caveats"><ul>{caveats or '<li>None recorded.</li>'}</ul></div></div>
  <div><h3>Recommended actions</h3><ol class="recs">{recs}</ol></div>
</div>"""

    doc = (SHELL
           .replace("__CSS__", (ASSETS / "dashboard.css").read_text())
           .replace("__JS__", (ASSETS / "dashboard.js").read_text())
           .replace("__CUBE__", json.dumps(cube, separators=(",", ":")))
           .replace("__TITLE__", _e(f.get("headline", "Analysis")))
           .replace("__HEADER__", _e(meta.get("header", "Subscription retention")))
           .replace("__META__", f"{date.today().isoformat()} · {_e(meta.get('csv',''))} · "
                                f"reviewer: {_e(meta.get('verdict','n/a'))} · "
                                f"{_e(meta.get('rounds',1))} round(s)")
           .replace("__HEADLINE__", _e(f.get("headline", "")))
           .replace("__QUESTION__", _e(meta.get("question", "")))
           .replace("__FINDINGS__", findings_html)
           .replace("__MODELPANEL__", model_panel)
           .replace("__BOTTOM__", bottom)
           .replace("__FOOTER__",
                    "Every figure recomputes in your browser from the row-level data "
                    "embedded in this file, so the filters and thresholds above are live "
                    "rather than pre-rendered. Nothing is fetched from the network. The "
                    "execution transcript saved alongside this file shows the code that "
                    "produced each number."))

    out_path.write_text(doc)
    return out_path
