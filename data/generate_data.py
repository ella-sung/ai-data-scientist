"""
Generates a synthetic SaaS subscription dataset for the AI data scientist to analyse.

Deliberately includes:
  - real causal signal (so a model can actually learn something)
  - missing values, duplicate rows, inconsistent category casing
  - one leakage column ('exit_survey_sent') that is only ever set for churners,
    so the pipeline's leakage check has something real to catch

Run:  python data/generate_data.py
"""

import numpy as np
import pandas as pd

RNG = np.random.default_rng(20260901)
N = 9000

PLANS = ["starter", "pro", "business", "enterprise"]
PLAN_WEIGHTS = [0.44, 0.32, 0.18, 0.06]
PLAN_BASE_MRR = {"starter": 29, "pro": 99, "business": 349, "enterprise": 1200}

REGIONS = ["North America", "Europe", "APAC", "LATAM"]
REGION_WEIGHTS = [0.46, 0.30, 0.17, 0.07]

INDUSTRIES = ["SaaS", "E-commerce", "Healthcare", "Financial services",
              "Education", "Manufacturing", "Media"]


def build() -> pd.DataFrame:
    plan = RNG.choice(PLANS, size=N, p=PLAN_WEIGHTS)
    region = RNG.choice(REGIONS, size=N, p=REGION_WEIGHTS)
    industry = RNG.choice(INDUSTRIES, size=N)

    signup = pd.to_datetime("2023-01-01") + pd.to_timedelta(
        RNG.integers(0, 900, size=N), unit="D"
    )
    tenure_days = (pd.to_datetime("2026-06-30") - signup).days.to_numpy()

    seat_lambda = np.select(
        [plan == "starter", plan == "pro", plan == "business", plan == "enterprise"],
        [2, 9, 34, 130],
    )
    seats = np.maximum(1, RNG.poisson(seat_lambda))

    base = np.array([PLAN_BASE_MRR[p] for p in plan], dtype=float)
    mrr = np.round(base * (0.75 + 0.5 * RNG.random(N)) * np.sqrt(seats), 2)

    contract_months = np.where(
        plan == "enterprise",
        RNG.choice([12, 24, 36], size=N, p=[0.5, 0.35, 0.15]),
        RNG.choice([1, 12], size=N, p=[0.72, 0.28]),
    )

    # --- engagement: the real driver of churn -------------------------------
    engagement = RNG.normal(0, 1, N) + 0.35 * np.log1p(seats) - 0.4 * (plan == "starter")
    monthly_logins = np.round(np.clip(RNG.gamma(2.2, 3.0, N) * (1 + 0.45 * engagement), 0, 120), 1)
    features_used = np.clip(np.round(2 + 4 * (engagement + RNG.normal(0, 0.8, N))), 0, 24).astype(int)
    days_since_login = np.round(np.clip(RNG.exponential(9, N) * np.exp(-0.35 * engagement), 0, 180)).astype(int)

    support_tickets = RNG.poisson(np.clip(1.4 - 0.35 * engagement, 0.1, None))
    payment_failures = RNG.poisson(np.where(plan == "starter", 0.30, 0.12))

    nps = np.clip(np.round(6.6 + 1.7 * engagement + RNG.normal(0, 1.9, N)), 0, 10)

    discount_pct = np.round(
        np.where(RNG.random(N) < 0.22, RNG.choice([5, 10, 15, 20, 25], size=N), 0), 1
    )

    # --- churn: logistic function of genuine drivers ------------------------
    logit = (
        -1.35
        - 0.95 * engagement
        + 0.030 * days_since_login
        + 0.24 * support_tickets
        + 0.58 * payment_failures
        - 0.145 * nps
        - 0.020 * (contract_months / 12) * 12
        - 0.0009 * tenure_days
        + 0.44 * (plan == "starter")
        - 0.30 * (plan == "enterprise")
        + 0.22 * (region == "LATAM")
        + RNG.normal(0, 0.55, N)
    )
    churned = (RNG.random(N) < 1 / (1 + np.exp(-logit))).astype(int)

    df = pd.DataFrame(
        {
            "customer_id": [f"C{100000 + i}" for i in range(N)],
            "signup_date": signup,
            "plan": plan,
            "region": region,
            "industry": industry,
            "seats": seats,
            "mrr": mrr,
            "contract_months": contract_months,
            "discount_pct": discount_pct,
            "monthly_logins_avg": monthly_logins,
            "features_used": features_used,
            "days_since_last_login": days_since_login,
            "support_tickets_90d": support_tickets,
            "payment_failures_90d": payment_failures,
            "nps_score": nps,
            "tenure_days": tenure_days,
            "churned": churned,
            # PLANTED LEAK: only ever sent after someone cancels.
            "exit_survey_sent": churned * RNG.binomial(1, 0.93, N),
        }
    )

    # --- realistic mess -----------------------------------------------------
    df.loc[RNG.random(N) < 0.11, "nps_score"] = np.nan
    df.loc[RNG.random(N) < 0.04, "industry"] = np.nan
    df.loc[RNG.random(N) < 0.02, "monthly_logins_avg"] = np.nan

    flip = RNG.random(N) < 0.03
    df.loc[flip, "region"] = df.loc[flip, "region"].str.upper()

    dupes = df.sample(70, random_state=7)
    df = pd.concat([df, dupes], ignore_index=True)
    df = df.sample(frac=1, random_state=11).reset_index(drop=True)

    return df


if __name__ == "__main__":
    frame = build()
    out = "data/subscriptions.csv"
    frame.to_csv(out, index=False)
    print(f"wrote {out}  rows={len(frame)}  cols={frame.shape[1]}")
    print(f"churn rate = {frame['churned'].mean():.3f}")
