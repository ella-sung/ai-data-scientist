"""
Builds the weekly report from the synthetic GoFundMe-style data with the model
stubbed out, so it costs nothing and is reproducible.

    python data/generate_gofundme_data.py
    python demo_gofundme.py

The analysis below is what the agent would produce. Fixed here so you can see
the deliverable and verify the plumbing before spending anything on the API.
"""

from __future__ import annotations

import json
from pathlib import Path

from dsagent import weekly
from dsagent.sandbox import Sandbox

DATA = Path("data").resolve()
OUT = Path("workspace/gofundme").resolve()

ANALYSIS = r"""
import json, os
import numpy as np, pandas as pd

w = pd.read_csv(os.path.join(DATA_DIR, "gfm_weekly.csv"))
a = pd.read_csv(os.path.join(DATA_DIR, "gfm_accounts.csv"))
weeks = sorted(w.week.unique())
LAST, PREV, FIRST = weeks[-1], weeks[-2], weeks[0]
cur, prv, fst = w[w.week == LAST], w[w.week == PREV], w[w.week == FIRST]
S = lambda d, c: float(d[c].sum())

# --- scale and take rate ---------------------------------------------------
gdv, rev = S(cur, "gdv"), S(cur, "net_revenue")
take_now = rev / gdv
take_then = S(fst, "net_revenue") / S(fst, "gdv")
tip_now, tip_then = S(cur, "tips_revenue") / gdv, S(fst, "tips_revenue") / S(fst, "gdv")
gdv_growth = gdv / S(fst, "gdv") - 1
rev_growth = rev / S(fst, "net_revenue") - 1
print(f"GDV ${gdv/1e6:.1f}M  net revenue ${rev/1e6:.2f}M  take {take_now:.2%}")
print(f"across the window: GDV {gdv_growth:+.1%}, revenue {rev_growth:+.1%}")
print(f"take rate {take_then:.2%} -> {take_now:.2%}; tips {tip_then:.2%} -> {tip_now:.2%}")

# revenue forgone if the tip rate had held
forgone = gdv * (tip_then - tip_now)
print(f"weekly revenue forgone to tip compression: ${forgone/1e3:.0f}K")

# --- liquidity -------------------------------------------------------------
funded = S(cur, "campaigns_fully_funded") / S(cur, "campaigns_created")
attain = gdv / S(cur, "goal_amount")
fast = S(cur, "campaigns_funded_24h") / S(cur, "campaigns_created")
avg_don = gdv / S(cur, "donations")
print(f"\nfunded {funded:.1%}  attainment {attain:.1%}  24h start {fast:.1%}  "
      f"avg donation ${avg_don:.2f}")

# does a fast start predict funding?
byc = w.groupby("category").apply(lambda d: pd.Series({
    "fast": d.campaigns_funded_24h.sum() / d.campaigns_created.sum(),
    "funded": d.campaigns_fully_funded.sum() / d.campaigns_created.sum(),
    "attain": d.gdv.sum() / d.goal_amount.sum(),
    "repeat_donor": d.returning_donors.sum() / d.donors.sum(),
    "avg_don": d.gdv.sum() / d.donations.sum(),
    "refund": d.refund_amount.sum() / d.gdv.sum(),
    "fraud": d.fraud_flagged.sum() / d.campaigns_created.sum(),
    "gdv": d.gdv.sum(),
}), include_groups=False).sort_values("gdv", ascending=False)
print("\nby category:"); print(byc.round(4))
corr = np.corrcoef(byc.fast, byc.attain)[0, 1]
print(f"corr(24h start, goal attainment) across categories = {corr:.2f}")

# --- growth loop -----------------------------------------------------------
viral = S(cur, "organizers_from_donors") / S(cur, "campaigns_created")
paid_c = cur[cur.is_paid_channel == 1]
paid_share = S(paid_c, "campaigns_created") / S(cur, "campaigns_created")
paid_cac = S(paid_c, "marketing_spend") / S(paid_c, "campaigns_created")
blended = S(cur, "marketing_spend") / S(cur, "campaigns_created")
print(f"\nviral share {viral:.1%}  paid share {paid_share:.1%}  "
      f"paid CAC ${paid_cac:.2f} vs blended ${blended:.2f}")

# --- trust -----------------------------------------------------------------
er = w[w.category == "Emergency relief"]
er_early = er[er.week <= weeks[13]]; er_late = er[er.week >= weeks[14]]
f_early = er_early.fraud_flagged.sum() / er_early.campaigns_created.sum()
f_late = er_late.fraud_flagged.sum() / er_late.campaigns_created.sum()
base = w[w.category != "Emergency relief"]
f_base = base.fraud_flagged.sum() / base.campaigns_created.sum()
print(f"\nemergency relief fraud rate {f_early:.3%} -> {f_late:.3%} "
      f"(everything else {f_base:.3%})")

# --- subscriptions ---------------------------------------------------------
# alive at the start of the window: signed up before it, and either never
# churned or churned inside it. Accounts that churned before week 0 are not
# part of the cohort and would understate NRR badly if included.
prior = a[(a.signup_week_index < 0) &
          (a.churn_week_index.isna() | (a.churn_week_index >= 0))]
nrr = prior[prior.is_active == 1].mrr.sum() / prior.mrr_prior.sum()
grr = np.minimum(prior[prior.is_active == 1].mrr,
                 prior[prior.is_active == 1].mrr_prior).sum() / prior.mrr_prior.sum()
logo = prior.is_active.mean()
print(f"\nNRR {nrr:.1%}  GRR {grr:.1%}  logo retention {logo:.1%}")

out = {
    "week": LAST, "gdv": gdv, "rev": rev,
    "take_now": take_now, "take_then": take_then,
    "tip_now": tip_now, "tip_then": tip_then,
    "gdv_growth": gdv_growth, "rev_growth": rev_growth, "forgone": forgone,
    "funded": funded, "attain": attain, "fast": fast, "avg_don": avg_don,
    "fast_attain_corr": float(corr),
    "viral": viral, "paid_share": paid_share, "paid_cac": paid_cac, "blended": blended,
    "er_fraud_early": f_early, "er_fraud_late": f_late, "base_fraud": f_base,
    "nrr": nrr, "grr": grr, "logo": logo,
    "by_category": {k: {m: round(float(v), 5) for m, v in r.items()}
                    for k, r in byc.iterrows()},
}
open("summary.json", "w").write(json.dumps(out, indent=2, default=str))
print("\nwrote summary.json")
"""


def main() -> int:
    sb = Sandbox(workdir=OUT, data_dir=DATA)
    res = sb.run(ANALYSIS)
    print(res.as_tool_result()[:3600])
    if not res.ok:
        return 1

    import pandas as pd
    s = json.loads((OUT / "summary.json").read_text())
    cube = weekly.build_weekly_cube(pd.read_csv(DATA / "gfm_weekly.csv"),
                                    pd.read_csv(DATA / "gfm_accounts.csv"))
    bc = s["by_category"]

    findings = {
        "headline": (f"Week of {s['week']}: donation volume is flat across the window "
                     f"while net revenue is down {abs(s['rev_growth'])*100:.0f}%. The gap is "
                     "entirely take rate."),
        "findings": [
            {"title": "Take rate is falling faster than volume is growing",
             "detail": (f"Take rate has gone from {s['take_then']*100:.2f}% to "
                        f"{s['take_now']*100:.2f}% of GDV, driven almost entirely by "
                        f"voluntary donor tips falling from {s['tip_then']*100:.2f}% to "
                        f"{s['tip_now']*100:.2f}%. Processing margin is stable, so this is a "
                        "checkout behaviour problem, not a cost problem. The decline is "
                        "monotonic week over week rather than seasonal, which is what "
                        "separates it from the volume line: GDV over this window is "
                        "confounded by the summer giving trough, but the tip rate falls "
                        "steadily through it. At current volume the compression costs about "
                        f"${s['forgone']/1e3:.0f}K per week on donations the platform is "
                        "already processing. None of this is visible on a volume chart, which "
                        "is the argument for putting take rate on the dashboard as a "
                        "first-class metric rather than deriving it on request."),
             "evidence": (f"tips {s['tip_then']*100:.2f}% to {s['tip_now']*100:.2f}% of GDV; "
                          f"net revenue {s['rev_growth']*100:+.1f}% over 27 weeks")},
            {"title": "A first-day donation is the strongest liquidity signal",
             "detail": (f"Only {s['funded']*100:.1f}% of campaigns reach 100% of goal, but "
                        f"campaigns collectively raise {s['attain']*100:.0f}% of the goals "
                        "they set, so partial funding is the norm rather than failure and the "
                        "fully-funded rate on its own is a misleading health measure. Across "
                        "categories the share of campaigns receiving a donation within 24 "
                        f"hours correlates {s['fast_attain_corr']:.2f} with eventual goal "
                        "attainment. Memorial campaigns start fastest and attain most; "
                        "education campaigns start slowest and attain least. That makes the "
                        "first day the highest-leverage moment on the platform."),
             "evidence": (f"{s['fast']*100:.1f}% of campaigns funded within 24h; "
                          f"attainment {s['attain']*100:.0f}%")},
            {"title": "Blended CAC hides what paid acquisition actually costs",
             "detail": (f"Only {s['paid_share']*100:.0f}% of campaigns come from paid "
                        f"channels. Blended cost per campaign is ${s['blended']:.2f}, but the "
                        f"real cost of a bought campaign is ${s['paid_cac']:.2f} — roughly "
                        f"{s['paid_cac']/s['blended']:.0f}x higher. Reporting the blended "
                        "figure would make paid acquisition look far cheaper than it is. "
                        f"Meanwhile {s['viral']*100:.0f}% of new campaigns are started by "
                        "people who first arrived as donors, which is the loop actually "
                        "driving growth."),
             "evidence": (f"paid CAC ${s['paid_cac']:.2f} vs blended ${s['blended']:.2f} "
                          f"at {s['paid_share']*100:.0f}% paid share")},
            {"title": "Fraud is concentrating in emergency relief and getting worse",
             "detail": (f"The share of emergency-relief campaigns flagged for fraud has risen "
                        f"from {s['er_fraud_early']*100:.3f}% to {s['er_fraud_late']*100:.3f}%, "
                        f"against {s['base_fraud']*100:.3f}% across every other category. "
                        "Disaster-driven categories are spiky and time-pressured, which is "
                        "exactly the environment bad actors exploit. Its refund rate is also "
                        f"the platform's highest at {bc['Emergency relief']['refund']*100:.2f}%. "
                        "For a donation platform this is not a cost line, it is the product: "
                        "donor trust is the asset being spent."),
             "evidence": "; ".join(
                 f"{k} fraud {v['fraud']*100:.3f}%, refunds {v['refund']*100:.2f}%"
                 for k, v in list(bc.items())[:3])},
            {"title": "The subscription line is growing through expansion, not new logos",
             "detail": (f"Net revenue retention on the pre-window cohort is {s['nrr']*100:.0f}% "
                        f"against gross retention of {s['grr']*100:.0f}% and logo retention of "
                        f"{s['logo']*100:.0f}%. The gap between NRR and GRR is expansion within "
                        "surviving accounts, which is carrying the line while account count "
                        "shrinks. That is a healthier position than the logo number alone "
                        "suggests, but it concentrates revenue in fewer customers."),
             "evidence": (f"NRR {s['nrr']*100:.0f}%, GRR {s['grr']*100:.0f}%, "
                          f"logo {s['logo']*100:.0f}%")},
        ],
        "caveats": [
            "Synthetic data. GoFundMe does not publish these figures; the structure "
            "reflects their public business model but every number here is invented.",
            "Take rate here counts donor tips plus processing revenue net of network "
            "cost. It excludes chargeback losses, fraud write-offs and support cost, so "
            "it is a gross take rate rather than a contribution margin.",
            "The 24-hour-start to attainment correlation is measured across seven "
            "category aggregates, not across campaigns. Seven points is far too few to "
            "treat as causal, and an early donation is plausibly a proxy for the "
            "organizer having a mobilised network rather than a cause of funding. "
            "Prompting a share will not manufacture the network.",
            "Week 0 falls in February and week 26 in August, so any first-to-last "
            "comparison of volume confounds trend with the summer giving trough. The "
            "tip-rate decline is stated instead because it is monotonic within the "
            "window and does not depend on that comparison.",
            "Channel attribution is last-touch, so organic almost certainly absorbs "
            "credit for demand paid channels created upstream. The gap between paid and "
            "blended CAC is real but its size is attribution-dependent.",
            "Fraud-flagged is a detection rate, not a fraud rate. A rise can mean more "
            "fraud or better detection, and these data cannot distinguish them.",
        ],
        "recommendations": [
            "Treat tip rate as an owned metric with a named owner and a weekly target. "
            "A/B the tip prompt at checkout before adding volume, since a 0.1pp recovery "
            "is worth more than a week of GDV growth at current margins.",
            "Build a first-24-hour intervention for campaigns with no donations: prompt "
            "the organizer to share, since that window predicts the outcome better than "
            "anything measurable later.",
            "Report paid CAC and paid share separately from blended CAC in this review, "
            "and stop quoting the blended figure in acquisition decisions.",
            "Escalate emergency-relief verification: manual review above a volume "
            "threshold during disaster surges, when both the fraud rate and payout "
            "pressure peak simultaneously.",
            "Add chargeback losses and fraud write-offs to the take-rate calculation so "
            "the reported margin reflects money actually kept.",
        ],
    }

    meta = {"header": "GoFundMe · weekly marketplace review",
            "verdict": "keep (demo: judge not run)"}

    (OUT / "cube.json").write_text(json.dumps(cube, separators=(",", ":")))
    (OUT / "findings.json").write_text(json.dumps(findings, indent=2))
    weekly.write_weekly_dashboard(findings, meta, cube, OUT / "weekly_report.html")
    print(f"\nwrote {OUT / 'weekly_report.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
