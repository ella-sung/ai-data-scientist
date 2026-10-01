"""
Runs the whole pipeline with the model stubbed out.

Use this first. It exercises the profiler, the validity checks, the sandbox and
both renderers using a hand-written analysis, so you can confirm everything
works and see what the deliverables look like before spending a cent on the API.

    python demo_no_api.py
"""

from __future__ import annotations

import json
from pathlib import Path

from dsagent import checks, outputs, profiler
from dsagent.sandbox import Sandbox

CSV = Path("data/subscriptions.csv").resolve()
OUT = Path("workspace/demo").resolve()

# This is the code an agent would have written. Here it is fixed, so the demo
# is reproducible and free.
ANALYSIS_CODE = r"""
import json, os
import numpy as np, pandas as pd
import matplotlib.pyplot as plt
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
from sklearn.inspection import permutation_importance

plt.rcParams.update({"figure.dpi": 140, "axes.grid": True, "grid.alpha": .25,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "font.size": 10})
RISK, HOLD, MUTE = "#A3324B", "#14655F", "#616C78"

df = pd.read_csv(os.path.join(DATA_DIR, "subscriptions.csv"))
print("loaded", df.shape)

# leakage + hygiene
LEAK = ["exit_survey_sent"]
df = df.drop_duplicates()
df["region"] = df["region"].str.title().replace({"Apac": "APAC", "Latam": "LATAM"})
print("after dedupe", df.shape)

y = df["churned"]
drop = ["churned", "customer_id", "signup_date"] + LEAK
X = pd.get_dummies(df.drop(columns=drop), columns=["plan", "region", "industry"],
                   dummy_na=True)

Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=.25, stratify=y, random_state=42)
clf = HistGradientBoostingClassifier(max_iter=250, learning_rate=.08, random_state=42)
clf.fit(Xtr, ytr)
auc = roc_auc_score(yte, clf.predict_proba(Xte)[:, 1])
print(f"held-out AUC = {auc:.4f}  (baseline 0.5)")

# 1. churn by plan
by_plan = df.groupby("plan")["churned"].agg(["mean", "size"]).reindex(
    ["starter", "pro", "business", "enterprise"])
print(by_plan)
fig, ax = plt.subplots(figsize=(8, 4))
ax.bar(by_plan.index, by_plan["mean"] * 100,
       color=[RISK if v > .1 else HOLD for v in by_plan["mean"]])
for i, (v, n) in enumerate(zip(by_plan["mean"], by_plan["size"])):
    ax.text(i, v * 100 + .5, f"{v*100:.1f}%  (n={n:,})", ha="center", fontsize=9)
ax.set_ylabel("churn rate (%)"); ax.set_xlabel("")
ax.set_title("Churn rate by plan tier")
ax.set_ylim(0, by_plan["mean"].max() * 100 * 1.22)
fig.tight_layout(); fig.savefig("figures/churn_by_plan.png"); plt.close(fig)

# 2. dormancy
bins = [0, 7, 14, 30, 60, 200]
labels = ["0-7", "8-14", "15-30", "31-60", "60+"]
df["dormancy"] = pd.cut(df["days_since_last_login"], bins=bins, labels=labels,
                        include_lowest=True)
dorm = df.groupby("dormancy", observed=True)["churned"].agg(["mean", "size"])
print(dorm)
fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(dorm.index.astype(str), dorm["mean"] * 100, marker="o", color=RISK, lw=2)
ax.fill_between(dorm.index.astype(str), 0, dorm["mean"] * 100, color=RISK, alpha=.08)
ax.set_ylabel("churn rate (%)"); ax.set_xlabel("days since last login")
ax.set_title("Churn rises sharply once an account goes quiet")
fig.tight_layout(); fig.savefig("figures/churn_by_dormancy.png"); plt.close(fig)

# 3. drivers
perm = permutation_importance(clf, Xte, yte, n_repeats=6, random_state=42,
                              scoring="roc_auc")
imp = pd.Series(perm.importances_mean, index=X.columns).sort_values()[-10:]
print(imp)
fig, ax = plt.subplots(figsize=(8, 4.6))
ax.barh(imp.index, imp.values, color=HOLD)
ax.set_xlabel("drop in held-out AUC when the column is shuffled")
ax.set_title("What the model actually relies on")
fig.tight_layout(); fig.savefig("figures/drivers.png"); plt.close(fig)

# 4. revenue at risk
top_decile = df.assign(p=clf.predict_proba(X)[:, 1]).nlargest(len(df) // 10, "p")
rev_at_risk = top_decile["mrr"].sum()
capture = top_decile["churned"].sum() / df["churned"].sum()
print(f"top decile: MRR ${rev_at_risk:,.0f}, captures {capture:.1%} of churners")

# --- export the row-level cube the dashboard filters over -----------------
df_out = df.copy()
df_out["risk"] = clf.predict_proba(X)[:, 1]
df_out["contract"] = pd.cut(df_out["contract_months"], [0, 1, 12, 999],
                            labels=["monthly", "annual", "multi-year"]).astype(str)
cube_cols = ["customer_id", "plan", "region", "contract", "mrr",
             "days_since_last_login", "churned", "risk"]
df_out[cube_cols].to_csv("cube_rows.csv", index=False)
imp.sort_values(ascending=False).to_csv("drivers.csv", header=["importance"])
print("cube rows written:", len(df_out))

summary = {
    "auc": round(float(auc), 4),
    "churn_rate": round(float(y.mean()), 4),
    "by_plan": {k: round(float(v), 4) for k, v in by_plan["mean"].items()},
    "dormancy": {str(k): round(float(v), 4) for k, v in dorm["mean"].items()},
    "mrr_at_risk": round(float(rev_at_risk), 2),
    "decile_capture": round(float(capture), 4),
    "monthly_mrr_total": round(float(df["mrr"].sum()), 2),
}
open("summary.json", "w").write(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
"""


def main() -> int:
    print("profiling…")
    card = profiler.profile(CSV, target="churned")
    print(f"  {card['n_rows']} rows, {card['n_cols']} cols, "
          f"{card['duplicate_rows']} duplicates")

    print("validity checks…")
    check = checks.run_all(str(CSV), "churned")
    print(checks.as_prompt_block(check))

    print("\nrunning the analysis in the sandbox…")
    sb = Sandbox(workdir=OUT, data_dir=CSV.parent)
    res = sb.run(ANALYSIS_CODE)
    print(res.as_tool_result()[:2500])
    if not res.ok:
        return 1

    s = json.loads((OUT / "summary.json").read_text())

    findings = {
        "headline": (
            f"Churn is concentrated in self-serve: starter accounts leave at "
            f"{s['by_plan']['starter']*100:.1f}% against {s['by_plan']['enterprise']*100:.1f}% "
            f"on enterprise."
        ),
        "kpis": [
            {"label": "Overall churn rate", "value": f"{s['churn_rate']*100:.1f}%",
             "context": f"{int(s['churn_rate']*9000):,} of 9,000 unique accounts"},
            {"label": "Model AUC (held out)", "value": f"{s['auc']:.3f}",
             "context": "against a coin-flip baseline of 0.500"},
            {"label": "MRR in the top risk decile", "value": f"${s['mrr_at_risk']:,.0f}",
             "context": f"{s['mrr_at_risk']/s['monthly_mrr_total']*100:.1f}% of total monthly revenue"},
            {"label": "Churners captured in that decile", "value": f"{s['decile_capture']*100:.0f}%",
             "context": "targeting 10% of accounts reaches this share"},
        ],
        "findings": [
            {"title": "Plan tier is the strongest structural split",
             "detail": ("Churn falls monotonically as plan value rises. Starter accounts "
                        f"churn at {s['by_plan']['starter']*100:.1f}%, roughly "
                        f"{s['by_plan']['starter']/s['by_plan']['enterprise']:.0f}x the enterprise "
                        "rate. This is partly a contract effect (most starter accounts are "
                        "month-to-month) and partly an engagement effect, since starter accounts "
                        "log in less and use fewer features."),
             "evidence": ", ".join(f"{k} {v*100:.1f}%" for k, v in s["by_plan"].items()),
             "figure": "figures/churn_by_plan.png"},
            {"title": "Dormancy is the earliest reliable warning",
             "detail": ("Churn climbs steeply with days since last login. Accounts quiet for "
                        f"more than 60 days churn at {s['dormancy']['60+']*100:.1f}%, against "
                        f"{s['dormancy']['0-7']*100:.1f}% for accounts active within the week. "
                        "Because login recency is observable daily, it is the practical trigger "
                        "for intervention rather than a post-hoc explanation."),
             "evidence": "; ".join(f"{k} days: {v*100:.1f}%" for k, v in s["dormancy"].items()),
             "figure": "figures/churn_by_dormancy.png"},
            {"title": "The model relies on behaviour, not demographics",
             "detail": ("Permutation importance on the held-out set is led by breadth of feature "
                        "use, NPS and account size, with login recency and support volume close "
                        "behind. Region and industry contribute almost nothing. That is "
                        "encouraging: the drivers are things the business can act on, not fixed "
                        "attributes of who the customer is."),
             "evidence": f"held-out AUC {s['auc']:.3f} against a 0.500 baseline",
             "figure": "figures/drivers.png"},
        ],
        "model": {
            "task": "Binary churn classification",
            "metric": "ROC AUC (held out)",
            "value": s["auc"],
            "baseline": 0.5,
            "beats_baseline": s["auc"] > 0.5,
            "excluded_features": ["exit_survey_sent", "customer_id", "signup_date"],
        },
        "caveats": [
            "exit_survey_sent was dropped before modelling. It is only ever set after an "
            "account cancels, so including it would have produced an AUC near 0.96 that "
            "meant nothing.",
            "140 duplicate rows were removed before splitting. Left in, they leak across "
            "the train/test boundary and inflate every metric.",
            "This is a cross-sectional snapshot, not a time-based split, so the numbers "
            "describe association rather than forecast performance on future cohorts.",
            "NPS is missing for 11% of accounts and missingness is not random; low-engagement "
            "accounts answer surveys less often.",
        ],
        "recommendations": [
            "Trigger a customer-success touch at 14 days of inactivity on any account above "
            "$100 MRR, rather than waiting for the renewal date.",
            "Route payment failures on starter and pro plans to a retry-plus-outreach flow; "
            "they carry the largest single-variable effect after dormancy.",
            "Offer annual terms at a discount to month-to-month starter accounts, since "
            "contract length shows an independent protective effect.",
            "Score the book weekly and work the top decile, which contains "
            f"{s['decile_capture']*100:.0f}% of eventual churners.",
        ],
    }

    meta = {"question": "Which customers churn, why, and what should we do about it?",
            "csv": CSV.name, "verdict": "keep (demo: judge not run)", "rounds": 1,
            "judge_reasons": []}

    import pandas as pd
    cube_df = pd.read_csv(OUT / "cube_rows.csv")
    drivers = pd.read_csv(OUT / "drivers.csv", index_col=0)["importance"]
    cube = outputs.build_cube(
        cube_df, cube_df["risk"],
        id_col="customer_id", plan_col="plan", region_col="region",
        contract_col="contract", mrr_col="mrr",
        dormancy_col="days_since_last_login", target_col="churned",
        drivers=list(drivers.items()),
    )

    (OUT / "findings.json").write_text(json.dumps(findings, indent=2))
    (OUT / "cube.json").write_text(json.dumps(cube, separators=(",", ":")))
    outputs.write_report(findings, meta, OUT / "report.md")
    outputs.write_dashboard(findings, meta, cube, OUT / "dashboard.html")
    print(f"\nwrote {OUT/'report.md'}\nwrote {OUT/'dashboard.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
