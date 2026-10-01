"""
Weekly operating report: cube builder and renderer.

The subscription explorer in outputs.py answers "who is at risk right now".
This answers a different question: "what changed this week, and where". It needs
a time axis, week-over-week deltas and two separate metric families, because a
marketplace and a subscription business do not share a definition of churn.

Output is one self-contained HTML file. CSS, JS and data are inlined, so it
works offline and can be emailed as a single attachment.
"""

from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path

ASSETS = Path(__file__).parent

MK_COLS = ["w", "cat", "reg", "ch", "camp", "funded", "fast", "goal", "gdv",
           "don", "donors", "retdon", "fromdon", "repeatorg", "tips", "procrev",
           "proccost", "rev", "refunds", "refamt", "cb", "fraud", "paydays",
           "paid", "spend"]
SUB_COLS = ["tier", "reg", "ch", "signup", "churn", "active", "tenure",
            "prior", "mrr", "cac"]

# CSV column -> cube field. Change this map, not the renderer, to adapt the
# report to a different marketplace.
SRC = {
    "camp": "campaigns_created", "funded": "campaigns_fully_funded",
    "fast": "campaigns_funded_24h", "goal": "goal_amount", "gdv": "gdv",
    "don": "donations", "donors": "donors", "retdon": "returning_donors",
    "fromdon": "organizers_from_donors", "repeatorg": "repeat_organizers",
    "tips": "tips_revenue", "procrev": "processing_revenue",
    "proccost": "processing_cost", "rev": "net_revenue",
    "refunds": "refunds", "refamt": "refund_amount", "cb": "chargebacks",
    "fraud": "fraud_flagged", "paydays": "payout_days",
    "paid": "is_paid_channel", "spend": "marketing_spend",
}
MONEY = {"goal", "gdv", "tips", "procrev", "proccost", "rev", "refamt", "spend"}
NEVER = 99999  # sentinel for "has not churned"


def build_weekly_cube(weekly, accounts, *, week_col="week", cat_col="category",
                      reg_col="region", ch_col="channel") -> dict:
    """
    Compact export the browser recomputes every KPI from.

    Categoricals become integer indices and money is rounded to whole units,
    which keeps a 27-week x 25-metric cube near 500 KB rather than several
    megabytes. Rates are never stored -- they are derived in the browser so that
    filtering recomputes them correctly instead of averaging pre-baked ratios.
    """
    weeks = sorted(weekly[week_col].astype(str).unique().tolist())
    wi = {w: i for i, w in enumerate(weeks)}

    order = lambda col, by: (weekly.groupby(col)[by].sum()
                             .sort_values(ascending=False).index.astype(str).tolist())
    cats = order(cat_col, SRC["gdv"])
    regs = order(reg_col, SRC["gdv"])
    chs = order(ch_col, SRC["camp"])
    ci = {v: i for i, v in enumerate(cats)}
    ri = {v: i for i, v in enumerate(regs)}
    hi = {v: i for i, v in enumerate(chs)}

    fields = [k for k in MK_COLS if k not in ("w", "cat", "reg", "ch")]
    missing = [SRC[k] for k in fields if SRC[k] not in weekly.columns]
    if missing:
        raise ValueError(f"weekly data is missing columns: {missing}")

    cols = weekly[[SRC[k] for k in fields]].to_numpy()
    keys = list(zip(weekly[week_col].astype(str), weekly[cat_col].astype(str),
                    weekly[reg_col].astype(str), weekly[ch_col].astype(str)))

    rows = []
    for (w, c, r, h), vals in zip(keys, cols):
        row = [wi[w], ci[c], ri[r], hi[h]]
        for k, v in zip(fields, vals):
            row.append(round(float(v)) if k in MONEY
                       else (round(float(v), 2) if k == "paydays" else int(v)))
        rows.append(row)

    tiers = sorted(accounts["tier"].astype(str).unique().tolist())
    sub_chs = sorted(accounts["acquisition_channel"].astype(str).unique().tolist())
    ti = {v: i for i, v in enumerate(tiers)}
    si = {v: i for i, v in enumerate(sub_chs)}

    sub_rows = []
    for t, r, h, sg, cw, ac, tn, pr, mr, cc in zip(
            accounts["tier"].astype(str), accounts["region"].astype(str),
            accounts["acquisition_channel"].astype(str),
            accounts["signup_week_index"], accounts["churn_week_index"],
            accounts["is_active"], accounts["tenure_weeks"],
            accounts["mrr_prior"], accounts["mrr"], accounts["cac"]):
        if str(r) not in ri:
            continue
        # NEVER_CHURNED must not collide with a real churn week. Accounts can
        # churn before week 0 (down to -103 here), so -1 is not a safe sentinel.
        sub_rows.append([ti[str(t)], ri[str(r)], si[str(h)], int(sg),
                         NEVER if cw != cw else int(cw), int(ac), int(tn),
                         round(float(pr), 2), round(float(mr), 2), round(float(cc), 2)])

    return {
        "weeks": weeks, "categories": cats, "regions": regs, "channels": chs,
        "cols": MK_COLS, "rows": rows,
        "sub": {"tiers": tiers, "channels": sub_chs, "cols": SUB_COLS, "rows": sub_rows},
    }


def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


SHELL = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>__CSS__</style></head>
<body><div class="wrap">

<header><div class="who">__HEADER__</div><div class="meta">__META__</div></header>
<p class="synthetic">__DISCLAIMER__</p>

<div class="weekbar">
  <button class="step" id="prev" type="button" aria-label="Previous week">&lsaquo;</button>
  <button class="step" id="next" type="button" aria-label="Next week">&rsaquo;</button>
  <h1 id="weeklabel"></h1>
</div>
<p class="scope"><span id="scope"></span> ·
  <button class="resetbtn" id="reset" type="button">reset to latest week</button></p>

<div id="filters"></div>
<div id="empty" hidden>Nothing recorded for this combination of week and filters.</div>

<div class="sechead"><h2>Marketplace scale</h2>
  <p>Gross donation volume is the top line. Take rate converts it into revenue,
     and it is the metric most easily hidden by a growing GDV.</p></div>
<div class="band" id="kpi-scale"></div>

<div class="sechead"><h2>Marketplace liquidity</h2>
  <p>Whether campaigns actually get funded. A platform that takes campaigns and
     does not fund them loses organizers regardless of how much volume it posts.</p></div>
<div class="band" id="kpi-liq"></div>

<div class="sechead"><h2>Growth loop</h2>
  <p>Donors becoming organizers is the engine. Blended CAC across a mostly
     organic mix is a vanity number, so paid CAC is shown on its own.</p></div>
<div class="band" id="kpi-loop"></div>

<div class="sechead"><h2>Trust and safety</h2>
  <p>Close to existential for a donation platform: the product only works while
     donors believe campaigns are real and organizers get paid quickly.</p></div>
<div class="band" id="kpi-trust"></div>

<div class="sechead"><h2>Nonprofit subscriptions</h2>
  <p>The recurring-revenue line, and the only place where retention metrics mean
     what they normally mean.</p></div>
<div class="band" id="kpi-sub"></div>

<div id="panels">
  <div class="panel full">
    <h3 id="trend-title"></h3>
    <p class="note">Click any point to jump the whole report to that week. The
      dashed line marks the week currently selected.</p>
    <div id="metric">
      <button class="chip" data-metric="gdv">GDV</button>
      <button class="chip" data-metric="rev">Net revenue</button>
      <button class="chip" data-metric="take">Take rate</button>
      <button class="chip" data-metric="avgDonation">Avg donation</button>
      <button class="chip" data-metric="fundedRate">Fully funded</button>
      <button class="chip" data-metric="repeatDonor">Repeat donors</button>
      <button class="chip" data-metric="paidCac">Paid CAC</button>
    </div>
    <div class="chart" id="c-trend"></div>
  </div>
  <div class="panel">
    <h3>Take rate, split by source</h3>
    <p class="note">Voluntary donor tips against payment-processing margin, both
      as a share of GDV. Volume growth can mask a falling tip rate entirely.</p>
    <div class="chart" id="c-take"></div>
    <div id="take-legend"></div>
  </div>
  <div class="panel">
    <h3>Trust by category, selected week</h3>
    <p class="note">Refund rate against the share of campaigns flagged for fraud.
      Disaster-driven categories attract both.</p>
    <div class="chart" id="c-trust"></div>
    <div id="trust-legend"></div>
  </div>
  <div class="panel full">
    <h3>Nonprofit retention by acquisition channel</h3>
    <p class="note">Share of accounts still subscribed, by weeks since signup.
      Channels that buy worse accounts separate early and never recover.</p>
    <div class="chart" id="c-curve"></div>
    <div id="curve-legend"></div>
  </div>
</div>

<div id="segwrap">
  <div class="head"><h3>Category detail for the selected week</h3>
    <p class="note">Refund rates above 1.2% are highlighted. Repeat rates differ
      structurally by category and are not a performance score.</p></div>
  <table id="segtable"></table>
</div>

<div id="movers">
  <h3>Biggest week-over-week movers</h3>
  <p class="note">Ranked by absolute change across GDV, take rate, refunds, fraud
    and paid CAC. Red means the move is in the wrong direction, so a rising
    refund rate reads red even though the arrow points up.</p>
  <ul id="mover-list"></ul>
</div>

__FINDINGS__
__BOTTOM__

<footer>__FOOTER__</footer>
</div>
<script>const CUBE = __CUBE__;</script>
<script>__JS__</script>
</body></html>"""

DISCLAIMER = (
    "Synthetic data. GoFundMe does not publish these figures. This models their "
    "publicly described business structure — no platform fee on personal "
    "campaigns, revenue from voluntary donor tips plus payment processing, and a "
    "separate nonprofit subscription line — with invented numbers. The KPI set is "
    "marketplace-native: GDV, take rate, liquidity, the viral loop, trust and "
    "safety, and net revenue retention on the subscription side."
)


def write_weekly_dashboard(findings: dict, meta: dict, cube: dict, out_path: Path) -> Path:
    f = findings or {}

    findings_html = "".join(
        f'<section class="finding"><h2>{_e(i.get("title"))}</h2>'
        f'<p>{_e(i.get("detail"))}</p>'
        + (f'<p class="evidence">{_e(i["evidence"])}</p>' if i.get("evidence") else "")
        + "</section>"
        for i in f.get("findings", [])
    )
    if findings_html:
        findings_html = ('<h2 style="font-size:18px;font-weight:500;margin:44px 0 0">'
                         "What the analysis found</h2>" + findings_html)

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
           .replace("__CSS__", (ASSETS / "weekly.css").read_text())
           .replace("__JS__", (ASSETS / "weekly.js").read_text())
           .replace("__CUBE__", json.dumps(cube, separators=(",", ":")))
           .replace("__TITLE__", _e(meta.get("header", "Weekly report")))
           .replace("__HEADER__", _e(meta.get("header", "Weekly operating report")))
           .replace("__META__", f"generated {date.today().isoformat()} · "
                                f"{_e(len(cube['weeks']))} weeks · "
                                f"reviewer: {_e(meta.get('verdict','n/a'))}")
           .replace("__DISCLAIMER__", DISCLAIMER)
           .replace("__FINDINGS__", findings_html)
           .replace("__BOTTOM__", bottom)
           .replace("__FOOTER__",
                    "Every figure recomputes in your browser from the week-level data "
                    "embedded in this file, so the week stepper and filters are live "
                    "rather than pre-rendered. Nothing is fetched from the network."))

    out_path.write_text(doc)
    return out_path
