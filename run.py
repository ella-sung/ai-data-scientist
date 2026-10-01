"""
The orchestrator. This is the file you actually run.

    python run.py --csv data/subscriptions.csv --target churned \
        --question "Which customers churn and why?"

Sequence:
    profile -> validity checks -> propose plans -> pick one
    -> [ analyse -> judge ] repeated until 'keep' or the round cap
    -> render report.md + dashboard.html
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from dsagent import checks, outputs, profiler, stages
from dsagent.sandbox import Sandbox

load_dotenv()


def log(msg: str) -> None:
    print(f"  {msg}", flush=True)


def banner(msg: str) -> None:
    print(f"\n{'=' * 66}\n{msg}\n{'=' * 66}", flush=True)


CUBE_COLS = ["id", "plan", "region", "contract", "mrr", "dorm", "churned", "risk"]


def build_cube_from_run(outdir: Path, csv_path: Path, target: str):
    """
    Assemble the dashboard cube from what the agent exported.

    Returns None if cube_rows.csv is absent or malformed, so the caller can fall
    back to the report alone rather than emitting a broken dashboard.
    """
    import pandas as pd

    rows_file = outdir / "cube_rows.csv"
    if not rows_file.exists():
        return None
    cube_df = pd.read_csv(rows_file)
    missing = [c for c in CUBE_COLS if c not in cube_df.columns]
    if missing:
        log(f"cube_rows.csv is missing columns: {missing}")
        return None
    cube_df = cube_df.dropna(subset=CUBE_COLS)
    if cube_df.empty:
        return None

    drivers_file = outdir / "drivers.csv"
    if drivers_file.exists():
        d = pd.read_csv(drivers_file)
        drivers = list(zip(d.iloc[:, 0].astype(str), d.iloc[:, 1].astype(float)))[:10]
    else:
        drivers = []

    return outputs.build_cube(
        cube_df, cube_df["risk"],
        id_col="id", plan_col="plan", region_col="region", contract_col="contract",
        mrr_col="mrr", dormancy_col="dorm", target_col="churned", drivers=drivers,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="data/subscriptions.csv")
    ap.add_argument("--target", default="churned")
    ap.add_argument("--question", default="Which customers churn, why, and what should we do about it?")
    ap.add_argument("--max-rounds", type=int, default=3, help="analyse/judge cycles before giving up")
    ap.add_argument("--max-turns", type=int, default=25, help="tool calls per analysis round")
    ap.add_argument("--num-plans", type=int, default=3)
    ap.add_argument("--backend", choices=["subprocess", "docker"], default="subprocess")
    ap.add_argument("--outdir", default=None)
    args = ap.parse_args()

    csv_path = Path(args.csv).resolve()
    if not csv_path.exists():
        print(f"No such file: {csv_path}\nRun: python data/generate_data.py")
        return 1

    run_id = time.strftime("run_%Y%m%d_%H%M%S")
    outdir = Path(args.outdir or f"workspace/{run_id}").resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    sandbox = Sandbox(workdir=outdir, data_dir=csv_path.parent, backend=args.backend)

    # ---- 1. profile -------------------------------------------------------
    banner("1. Profiling the data")
    card = profiler.profile(csv_path, target=args.target)
    card_text = profiler.as_prompt_block(card)
    log(f"{card['n_rows']} rows, {card['n_cols']} columns, "
        f"{card['duplicate_rows']} duplicate rows")

    # ---- 2. validity checks ----------------------------------------------
    banner("2. Validity checks (deterministic, no model involved)")
    check = checks.run_all(str(csv_path), args.target)
    check_text = checks.as_prompt_block(check)
    for line in check_text.splitlines():
        log(line)

    # ---- 3. plan ----------------------------------------------------------
    banner(f"3. Proposing {args.num_plans} analysis plans")
    plans = stages.propose_plans(card_text, check_text, args.question, args.num_plans)
    for i, p in enumerate(plans):
        log(f"[{i}] {p.get('title')} ({p.get('expected_cost','?')} cost)")
    plan = stages.choose_plan(plans, args.question)
    plan["_csv_name"] = csv_path.name
    log(f"chosen: {plan.get('title')} -- {plan.get('_why_chosen','')}")

    # ---- 4. analyse / judge loop -----------------------------------------
    feedback, verdict, result, judgement = None, "drop", None, {}
    for rnd in range(1, args.max_rounds + 1):
        banner(f"4. Analysis round {rnd} of {args.max_rounds}")
        result = stages.run_analysis(
            plan, card_text, check_text, args.question, sandbox,
            max_turns=args.max_turns, feedback=feedback,
            on_step=lambda s: log(
                f"  step {s['turn']}: {'ok ' if s['ok'] else 'ERR'} {s['purpose'][:70]}"),
        )
        log(f"finished in {result['turns_used']} turns")

        if result.get("findings") is None:
            feedback = "Your final message was not valid JSON in the required shape."
            log("could not parse findings JSON; retrying")
            continue

        banner(f"5. Review of round {rnd}")
        judgement = stages.judge(result, check_text, args.question)
        verdict = judgement.get("verdict", "fix")
        log(f"verdict: {verdict.upper()}")
        for r in judgement.get("reasons", []):
            log(f"  - {r}")

        if verdict == "keep":
            break
        feedback = "\n".join(
            judgement.get("required_fixes", []) + judgement.get("unsupported_claims", [])
        ) or "The reviewer rejected the work. Re-examine your numbers."
        if verdict == "drop":
            log("reviewer said drop; retrying from the plan")

    # ---- 5. render --------------------------------------------------------
    banner("6. Writing the report and dashboard")
    if not result or result.get("findings") is None:
        log("No usable findings were produced. Inspect the transcript below.")
        (outdir / "transcript.json").write_text(
            json.dumps(result or {}, indent=2, default=str))
        return 2

    meta = {
        "question": args.question,
        "csv": csv_path.name,
        "verdict": verdict,
        "rounds": rnd,
        "judge_reasons": judgement.get("reasons", []),
    }
    findings = result["findings"]

    (outdir / "findings.json").write_text(json.dumps(findings, indent=2))
    (outdir / "transcript.json").write_text(json.dumps(result, indent=2, default=str))
    (outdir / "plan.json").write_text(json.dumps(plan, indent=2))
    (outdir / "checks.json").write_text(json.dumps(check, indent=2))

    cube = build_cube_from_run(outdir, csv_path, args.target)
    if cube is None:
        log("cube_rows.csv missing; writing the report only")
        report = outputs.write_report(findings, meta, outdir / "report.md")
        print(f"\n  report {report}\n")
        return 3

    (outdir / "cube.json").write_text(json.dumps(cube, separators=(",", ":")))
    report = outputs.write_report(findings, meta, outdir / "report.md")
    dash = outputs.write_dashboard(findings, meta, cube, outdir / "dashboard.html")

    # keep a stable copy of the newest run
    latest = Path("workspace/latest")
    if latest.exists():
        shutil.rmtree(latest)
    shutil.copytree(outdir, latest)

    banner("Done")
    print(f"  report     {report}")
    print(f"  dashboard  {dash}")
    print(f"  verdict    {verdict}")
    print(f"\n  open workspace/latest/dashboard.html in a browser\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
