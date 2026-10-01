"""
Deterministic data profiling. No LLM involved.

This runs BEFORE the model sees anything. It produces a compact 'data card'
that gets pasted into every prompt, so the model reasons about real column
names, real types and real distributions instead of guessing.

Keeping this deterministic matters: if the model had to profile the data
itself it would burn turns and occasionally hallucinate a column.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


MAX_LEVELS = 8  # top-k categories to report per column


def _column_card(s: pd.Series) -> dict:
    card: dict = {
        "dtype": str(s.dtype),
        "null_pct": round(float(s.isna().mean()) * 100, 2),
        "n_unique": int(s.nunique(dropna=True)),
    }

    if pd.api.types.is_numeric_dtype(s) and s.notna().any():
        q = s.quantile([0, 0.25, 0.5, 0.75, 1.0])
        card["stats"] = {
            "min": round(float(q.iloc[0]), 3),
            "p25": round(float(q.iloc[1]), 3),
            "median": round(float(q.iloc[2]), 3),
            "p75": round(float(q.iloc[3]), 3),
            "max": round(float(q.iloc[4]), 3),
            "mean": round(float(s.mean()), 3),
        }
    elif s.notna().any():
        counts = s.value_counts().head(MAX_LEVELS)
        card["top_values"] = {str(k): int(v) for k, v in counts.items()}

    return card


def profile(csv_path: str | Path, target: str | None = None) -> dict:
    """Read a CSV and return a compact, promptable description of it."""
    path = Path(csv_path)
    df = pd.read_csv(path)

    card = {
        "file": path.name,
        "n_rows": int(len(df)),
        "n_cols": int(df.shape[1]),
        "duplicate_rows": int(df.duplicated().sum()),
        "columns": {c: _column_card(df[c]) for c in df.columns},
        "likely_id_columns": [
            c for c in df.columns if df[c].nunique(dropna=True) > 0.95 * len(df)
        ],
        "likely_date_columns": [
            c for c in df.columns
            if df[c].dtype == object and _looks_like_date(df[c])
        ],
    }

    if target and target in df.columns:
        vc = df[target].value_counts(normalize=True, dropna=False)
        card["target"] = {
            "name": target,
            "distribution": {str(k): round(float(v), 4) for k, v in vc.head(10).items()},
            "is_binary": bool(df[target].nunique(dropna=True) == 2),
        }

    return card


def _looks_like_date(s: pd.Series) -> bool:
    sample = s.dropna().head(50)
    if sample.empty:
        return False
    try:
        parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
    except Exception:
        return False
    return bool(parsed.notna().mean() > 0.9)


def as_prompt_block(card: dict) -> str:
    """Render the card as text small enough to paste into every prompt."""
    return json.dumps(card, indent=2, default=str)


if __name__ == "__main__":
    import sys

    tgt = sys.argv[2] if len(sys.argv) > 2 else None
    print(as_prompt_block(profile(sys.argv[1], tgt)))
