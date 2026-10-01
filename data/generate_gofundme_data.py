"""
SYNTHETIC data modelled on GoFundMe's publicly described business structure.
Not GoFundMe's real data -- their figures are private. The metric set, the
seasonality and the channel economics are plausible; every number is invented.

Why these KPIs and not churn and CAC:

  GoFundMe is a two-sided donation marketplace and a payments business, not a
  subscription business. The metrics that govern it are the marketplace ones:
  gross donation volume, take rate, marketplace liquidity (do campaigns actually
  get funded), the viral loop (do donors become organizers), and trust (refunds,
  chargebacks, fraud, payout speed). Trust is close to existential here -- the
  whole platform rests on donors believing campaigns are real.

  CAC survives only in a narrow form. Blended CAC across an acquisition mix that
  is ~58% organic is a vanity number, so this tracks paid share of acquisition
  and CAC on paid channels only.

  Real churn lives on the nonprofit subscription line, and even there net revenue
  retention is the standard measure rather than gross logo churn.

Writes:
  data/gfm_weekly.csv    week x category x region x channel
  data/gfm_accounts.csv  nonprofit subscription accounts

Run:  python data/generate_gofundme_data.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RNG = np.random.default_rng(20260215)

N_WEEKS = 27
WEEK_0 = pd.Timestamp("2026-02-23")

CATEGORIES = ["Medical", "Memorial", "Emergency relief", "Education",
              "Nonprofit", "Community & sports", "Animals"]
CAT_SHARE = np.array([0.31, 0.17, 0.14, 0.11, 0.10, 0.11, 0.06])
CAT_REPEAT = {"Medical": 0.22, "Memorial": 0.06, "Emergency relief": 0.19,
              "Education": 0.34, "Nonprofit": 0.61, "Community & sports": 0.41,
              "Animals": 0.29}
CAT_GOAL = {"Medical": 14000, "Memorial": 12000, "Emergency relief": 9000,
            "Education": 6500, "Nonprofit": 11000, "Community & sports": 7000,
            "Animals": 4800}
# share of goal a typical campaign in this category actually reaches
CAT_ATTAIN = {"Medical": 0.34, "Memorial": 0.55, "Emergency relief": 0.38,
              "Education": 0.41, "Nonprofit": 0.52, "Community & sports": 0.46,
              "Animals": 0.44}
CAT_DONATION = {"Medical": 71, "Memorial": 84, "Emergency relief": 63,
                "Education": 55, "Nonprofit": 92, "Community & sports": 48,
                "Animals": 44}
# Share of campaigns receiving a donation on day one. Categories where the
# organizer already has a mobilised network start fast; cold categories do not.
# Attainment is made to depend on this, so a first-day donation genuinely
# predicts funding rather than being an incidental correlation.
CAT_FAST = {"Medical": 0.61, "Memorial": 0.83, "Emergency relief": 0.55,
            "Education": 0.44, "Nonprofit": 0.74, "Community & sports": 0.52,
            "Animals": 0.47}

REGIONS = ["United States", "Canada", "United Kingdom", "Australia", "Western Europe"]
REG_SHARE = np.array([0.63, 0.11, 0.13, 0.06, 0.07])

CHANNELS = ["Organic & viral", "Paid search", "Paid social", "Partnerships", "Brand & direct"]
CH_SHARE = np.array([0.58, 0.14, 0.13, 0.09, 0.06])
CH_CPA = {"Organic & viral": 0.0, "Paid search": 34.0, "Paid social": 61.0,
          "Partnerships": 22.0, "Brand & direct": 12.0}
CH_QUALITY = {"Organic & viral": 1.10, "Paid search": 0.98, "Paid social": 0.74,
              "Partnerships": 1.04, "Brand & direct": 1.00}
PAID = {"Paid search", "Paid social", "Partnerships", "Brand & direct"}

TIERS = ["Essentials", "Growth", "Enterprise"]
TIER_SHARE = np.array([0.55, 0.34, 0.11])
TIER_MRR = {"Essentials": 249, "Growth": 899, "Enterprise": 3400}
TIER_CHURN = {"Essentials": 0.0135, "Growth": 0.0072, "Enterprise": 0.0028}


def seasonality(w: int) -> float:
    month = (WEEK_0 + pd.Timedelta(weeks=w)).month
    return {1: 0.92, 2: 0.95, 3: 1.00, 4: 1.02, 5: 1.00, 6: 0.94,
            7: 0.88, 8: 0.89, 9: 1.01, 10: 1.06, 11: 1.18, 12: 1.34}[month]


def tip_rate(w: int) -> float:
    """
    Voluntary donor tips are the main revenue line. PLANTED: the tip rate
    compresses steadily across the window as more donors opt out at checkout.
    Volume keeps growing, so the decline is invisible unless take rate is
    tracked as its own KPI -- which is the point of putting it on the dashboard.
    """
    return 0.0298 - 0.00018 * w


def build_weekly() -> pd.DataFrame:
    rows = []
    base_campaigns = 20500

    for w in range(N_WEEKS):
        week = (WEEK_0 + pd.Timedelta(weeks=w)).date().isoformat()
        s = seasonality(w)
        growth = 1 + 0.0035 * w
        tip = tip_rate(w)

        for ci, cat in enumerate(CATEGORIES):
            for ri, reg in enumerate(REGIONS):
                for hi, ch in enumerate(CHANNELS):
                    share = CAT_SHARE[ci] * REG_SHARE[ri] * CH_SHARE[hi]
                    ramp = 1 + 0.06 * (w - 17) if (ch == "Paid social" and w >= 18) else 1.0
                    drift = RNG.normal(1.0, 0.022)

                    n_camp = RNG.poisson(base_campaigns * share * s * growth * drift * ramp)
                    if n_camp < 3:
                        continue
                    # emergency relief is disaster-driven and spiky
                    surge = cat == "Emergency relief" and RNG.random() < 0.10
                    if surge:
                        n_camp = int(n_camp * RNG.uniform(1.6, 3.2))

                    # ---- liquidity: goals, attainment, funded campaigns -----
                    goal = CAT_GOAL[cat] * RNG.normal(1.0, 0.06)
                    fast_rate = np.clip(CAT_FAST[cat] * CH_QUALITY[ch]
                                        * RNG.normal(1.0, 0.04), 0.05, 0.97)
                    # day-one traction lifts eventual attainment
                    attain = (CAT_ATTAIN[cat] * (0.55 + 0.62 * fast_rate)
                              * RNG.normal(1.0, 0.05) * s)
                    raised_per = goal * attain
                    gdv = n_camp * raised_per
                    fully_funded = RNG.binomial(n_camp, np.clip(attain * 0.36, 0.01, 0.9))
                    # a campaign with a donation in 24h is far likelier to fund
                    fast_start = RNG.binomial(n_camp, fast_rate)

                    # ---- donations and donors -------------------------------
                    avg_don = CAT_DONATION[cat] * RNG.normal(1.0, 0.05)
                    n_don = max(int(gdv / avg_don), 1)
                    donors = int(n_don * RNG.uniform(0.86, 0.94))
                    returning_donors = RNG.binomial(donors, np.clip(
                        0.27 * CH_QUALITY[ch] * RNG.normal(1.0, 0.05), 0.02, 0.8))

                    # ---- revenue and margin ---------------------------------
                    tips = gdv * tip * RNG.normal(1.0, 0.03)
                    # 2.9% + $0.30 charged, ~2.5% + $0.20 paid to networks
                    processing_rev = gdv * 0.029 + 0.30 * n_don
                    processing_cost = gdv * 0.0251 + 0.21 * n_don
                    net_revenue = tips + processing_rev - processing_cost

                    # ---- viral loop -----------------------------------------
                    # organizers whose first contact with the platform was donating
                    from_donors = RNG.binomial(
                        n_camp, np.clip(0.41 if ch == "Organic & viral" else 0.12, 0, 1))
                    repeat_org = RNG.binomial(n_camp, min(CAT_REPEAT[cat] * CH_QUALITY[ch], 0.95))

                    # ---- trust and safety -----------------------------------
                    # PLANTED: emergency relief attracts fraud, and worsens late
                    fraud_rate = 0.0011
                    if cat == "Emergency relief":
                        fraud_rate = 0.0026 * (1 + 0.10 * max(w - 14, 0))
                    fraud = RNG.binomial(n_camp, min(fraud_rate, 0.2))
                    refund_rate = 0.0062 + (0.010 if cat == "Emergency relief" else 0)
                    refunds = RNG.binomial(n_don, min(refund_rate, 0.3))
                    refund_amt = refunds * avg_don * RNG.normal(1.0, 0.08)
                    chargebacks = RNG.binomial(n_don, 0.0016)
                    payout_days = float(np.clip(RNG.normal(3.1 + (0.9 if surge else 0), 0.35), 1, 12))

                    # ---- acquisition cost -----------------------------------
                    cpa = CH_CPA[ch] * RNG.normal(1.0, 0.09)
                    if ch == "Paid social" and w >= 18:
                        cpa *= 1 + 0.045 * (w - 17)
                    spend = n_camp * cpa

                    rows.append({
                        "week": week, "category": cat, "region": reg, "channel": ch,
                        "campaigns_created": int(n_camp),
                        "campaigns_fully_funded": int(fully_funded),
                        "campaigns_funded_24h": int(fast_start),
                        "goal_amount": round(n_camp * goal, 2),
                        "gdv": round(gdv, 2),
                        "donations": int(n_don),
                        "donors": int(donors),
                        "returning_donors": int(returning_donors),
                        "organizers_from_donors": int(from_donors),
                        "repeat_organizers": int(repeat_org),
                        "tips_revenue": round(tips, 2),
                        "processing_revenue": round(processing_rev, 2),
                        "processing_cost": round(processing_cost, 2),
                        "net_revenue": round(net_revenue, 2),
                        "refunds": int(refunds),
                        "refund_amount": round(refund_amt, 2),
                        "chargebacks": int(chargebacks),
                        "fraud_flagged": int(fraud),
                        "payout_days": round(payout_days, 2),
                        "is_paid_channel": int(ch in PAID),
                        "marketing_spend": round(spend, 2),
                    })

    return pd.DataFrame(rows)


def build_accounts() -> pd.DataFrame:
    """Nonprofit subscription accounts. NRR needs a prior-period MRR per account."""
    n = 5200
    tier = RNG.choice(TIERS, size=n, p=TIER_SHARE)
    region = RNG.choice(REGIONS, size=n, p=REG_SHARE)
    channel = RNG.choice(["Paid search", "Paid social", "Partnerships",
                          "Brand & direct", "Outbound sales"],
                         size=n, p=[0.24, 0.16, 0.23, 0.14, 0.23])
    signup_week = RNG.integers(-104, N_WEEKS, size=n)

    mrr_prior = np.round(np.array([TIER_MRR[t] for t in tier], dtype=float)
                         * RNG.normal(1.0, 0.22, n).clip(0.5, 2.2), 2)
    # seat and usage expansion, occasionally downgrades
    move = RNG.normal(1.045, 0.11, n).clip(0.55, 1.9)
    mrr = np.round(mrr_prior * move, 2)

    cac_base = {"Paid search": 780, "Paid social": 1450, "Partnerships": 410,
                "Brand & direct": 260, "Outbound sales": 2100}
    cac = np.round(np.array([cac_base[c] for c in channel])
                   * RNG.normal(1.0, 0.20, n).clip(0.4, 2.5), 2)

    hazard = np.array([TIER_CHURN[t] for t in tier])
    hazard *= np.where(channel == "Paid social", 1.55, 1.0)
    hazard *= np.where(channel == "Outbound sales", 0.85, 1.0)

    # An account can churn before week 0. Recording that is what makes the
    # retention cohort correct: NRR must be measured on accounts that were
    # actually alive at the start of the window, not on everyone ever signed up.
    churn_week = np.full(n, np.nan)
    for i in range(n):
        wk = signup_week[i] + RNG.geometric(hazard[i])
        if wk <= N_WEEKS - 1:
            churn_week[i] = wk

    active = np.isnan(churn_week)
    tenure = np.where(active, N_WEEKS - 1 - signup_week, churn_week - signup_week)

    return pd.DataFrame({
        "account_id": [f"NP{200000 + i}" for i in range(n)],
        "tier": tier, "region": region, "acquisition_channel": channel,
        "signup_week_index": signup_week, "churn_week_index": churn_week,
        "is_active": active.astype(int),
        "tenure_weeks": np.maximum(tenure, 0).astype(int),
        "mrr_prior": mrr_prior, "mrr": mrr, "cac": cac,
    })


if __name__ == "__main__":
    wk = build_weekly()
    wk.to_csv("data/gfm_weekly.csv", index=False)
    ac = build_accounts()
    ac.to_csv("data/gfm_accounts.csv", index=False)

    print(f"data/gfm_weekly.csv    {len(wk):,} rows x {wk.shape[1]} cols "
          f"({wk.week.nunique()} weeks)")
    print(f"data/gfm_accounts.csv  {len(ac):,} rows "
          f"({ac.is_active.mean():.1%} active)")
    last = wk[wk.week == wk.week.max()]
    tr = last.net_revenue.sum() / last.gdv.sum()
    first = wk[wk.week == wk.week.min()]
    print(f"\nlatest week {wk.week.max()}")
    print(f"  GDV               ${last.gdv.sum()/1e6:.1f}M")
    print(f"  net revenue       ${last.net_revenue.sum()/1e6:.2f}M")
    print(f"  take rate         {tr:.2%}  (week 0: "
          f"{first.net_revenue.sum()/first.gdv.sum():.2%})")
    print(f"  avg donation      ${last.gdv.sum()/last.donations.sum():.2f}")
    print(f"  fully funded      {last.campaigns_fully_funded.sum()/last.campaigns_created.sum():.1%}")
    print(f"  repeat donors     {last.returning_donors.sum()/last.donors.sum():.1%}")
    print(f"  refund rate       {last.refund_amount.sum()/last.gdv.sum():.2%}")
    print(f"  fraud flagged     {last.fraud_flagged.sum()/last.campaigns_created.sum():.3%}")
