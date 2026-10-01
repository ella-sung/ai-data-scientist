"""
Validity gate. Plain Python, no LLM.

These run before the model is allowed to spend effort, and their results are
fed into the prompt. The model may interpret them; it may never certify itself
as clean. That separation is the difference between a system you can trust and
one that confidently hands you a broken answer.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

LEAK_AUC_THRESHOLD = 0.90


def _auc(scores: np.ndarray, labels: np.ndarray) -> float:
    """Rank-based AUC. No sklearn import needed, handles ties correctly."""
    mask = ~np.isnan(scores)
    scores, labels = scores[mask], labels[mask]
    pos, neg = labels.sum(), (1 - labels).sum()
    if pos == 0 or neg == 0:
        return 0.5
    ranks = pd.Series(scores).rank().to_numpy()
    return float((ranks[labels == 1].sum() - pos * (pos + 1) / 2) / (pos * neg))


def run_all(csv_path: str, target: str) -> dict:
    df = pd.read_csv(csv_path)
    y = df[target].to_numpy()
    findings: dict = {"target": target, "n_rows": len(df)}

    # 1. duplicates -- inflate any metric and leak across a random split
    dupe_mask = df.duplicated(keep=False)
    findings["duplicate_rows"] = int(dupe_mask.sum())

    # 2. suspiciously predictive single columns
    suspects = []
    for col in df.columns:
        if col == target:
            continue
        s = df[col]
        if pd.api.types.is_numeric_dtype(s):
            score = s.to_numpy(dtype=float)
        elif s.nunique(dropna=True) <= 30:
            score = s.astype("category").cat.codes.to_numpy(dtype=float)
        else:
            continue
        auc = max(_auc(score, y), 1 - _auc(score, y))
        if auc >= LEAK_AUC_THRESHOLD:
            suspects.append({"column": col, "univariate_auc": round(auc, 4)})
    findings["leakage_suspects"] = sorted(
        suspects, key=lambda d: -d["univariate_auc"]
    )

    # 3. columns that are constant within one class -- the classic post-hoc field
    one_sided = []
    for col in df.columns:
        if col == target or df[col].nunique(dropna=True) > 20:
            continue
        ct = pd.crosstab(df[col], df[target])
        if ct.shape[1] == 2 and ((ct.min(axis=1) == 0).mean() == 1.0):
            one_sided.append(col)
    findings["one_sided_columns"] = one_sided

    # 4. trivial baselines the analysis must beat
    majority = float(max(np.mean(y), 1 - np.mean(y)))
    findings["baselines"] = {
        "majority_class_accuracy": round(majority, 4),
        "positive_rate": round(float(np.mean(y)), 4),
        "random_auc": 0.5,
    }

    findings["verdict"] = (
        "clean" if not findings["leakage_suspects"] and not one_sided else "review_required"
    )
    return findings


def as_prompt_block(findings: dict) -> str:
    lines = [f"Rows: {findings['n_rows']}  Duplicates: {findings['duplicate_rows']}"]
    b = findings["baselines"]
    lines.append(
        f"Baselines to beat: majority-class accuracy {b['majority_class_accuracy']}, "
        f"AUC 0.5. Positive rate {b['positive_rate']}."
    )
    if findings["leakage_suspects"]:
        lines.append("LEAKAGE SUSPECTS (single column predicts the target almost perfectly):")
        for s in findings["leakage_suspects"]:
            lines.append(f"  - {s['column']}  univariate AUC {s['univariate_auc']}")
    if findings["one_sided_columns"]:
        lines.append(
            "COLUMNS THAT ONLY EVER OCCUR IN ONE CLASS (almost certainly recorded "
            "after the outcome): " + ", ".join(findings["one_sided_columns"])
        )
    if findings["verdict"] == "clean":
        lines.append("No leakage detected.")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys, json
    print(json.dumps(run_all(sys.argv[1], sys.argv[2]), indent=2))
