"""
The three model-driven stages: PLAN, ANALYSE, JUDGE.

Each is a separate call with its own system prompt. Keeping the judge separate
from the analyst is deliberate -- the judge sees the artifacts, not the
analyst's reasoning, so it cannot be talked into approving a bad result.
"""

from __future__ import annotations

import json

from . import llm

CUBE_CONTRACT = """
Before you finish you MUST write a file called cube_rows.csv in the working
directory. The dashboard filters over it in the browser, so it has to have
exactly these eight columns, with exactly these names, one row per account
AFTER de-duplication:

  id        a stable account identifier
  plan      the primary segment (plan tier)
  region    the geographic segment
  contract  the commitment segment, bucketed to monthly / annual / multi-year
  mrr       monthly revenue, numeric
  dorm      days since last activity, integer
  churned   the outcome, 0 or 1
  risk      your model's predicted probability for that row, 0 to 1

Also write drivers.csv with two columns, feature and importance, holding the
top 10 permutation importances on the held-out set. Keep the cube under 50,000
rows; sample if the data is larger.
"""

FINDINGS_SCHEMA = """
{
  "headline": "one sentence a stakeholder could read on its own",
  "kpis": [
    {"label": "short label", "value": "formatted value", "context": "what it means, <=12 words"}
  ],
  "findings": [
    {"title": "short title",
     "detail": "2-4 sentences explaining the finding and its size",
     "evidence": "the specific numbers that support it",
     "figure": "figures/name.png or null"}
  ],
  "model": {"task": "...", "metric": "...", "value": 0.0, "baseline": 0.0,
            "beats_baseline": true, "excluded_features": ["..."]},
  "caveats": ["things a reader must know before acting on this"],
  "recommendations": ["concrete action, not 'investigate further'"]
}
"""

ANALYST_SYSTEM = """You are a senior data scientist. You work by running code, \
looking at the actual output, and adjusting. You never state a number you have \
not computed.

Rules you follow without being reminded:
- Drop any column flagged as a leakage suspect before modelling, and say so.
- De-duplicate before splitting. Split before fitting anything.
- Always compare against the stated trivial baseline. A model that does not \
beat it is a negative result and you report it as one.
- Every chart you save must be legible: labelled axes, a title, readable tick \
labels. Save to figures/ as PNG at dpi=140, figsize around (8, 4.5).
- Report effect sizes, not just significance. "Starter plans churn at 23.7% vs \
1.0% for enterprise" is useful; "plan is significant" is not.
- When you are done, output the findings JSON and nothing else."""

PLANNER_SYSTEM = """You are a principal data scientist scoping an analysis. \
You propose approaches that can be executed and checked, not vague directions. \
Each plan must name the specific columns it uses and the specific number that \
would tell you it worked."""

JUDGE_SYSTEM = """You are a demanding reviewer. You see only the artifacts: the \
code that ran, its output, and the findings produced. You do not see the \
analyst's reasoning and you do not give benefit of the doubt.

Return exactly one verdict:
  "keep"  - the work is sound and the findings are supported by the output shown
  "fix"   - salvageable, but something specific is wrong or missing
  "drop"  - fundamentally unsound; start over

You must cite the specific evidence for your verdict. Reject any claim whose \
number does not appear in the execution output. Reject any model that did not \
beat its baseline unless it is explicitly reported as a negative result. Reject \
the work if cube_rows.csv or drivers.csv was never written, since the dashboard \
cannot be built without them."""


def propose_plans(data_card: str, check_block: str, question: str, n: int = 3) -> list[dict]:
    user = f"""Business question:
{question}

Data profile:
{data_card}

Validity checks already run:
{check_block}

Propose {n} distinct analysis plans. They should differ in approach, not just
in wording. Return a JSON list of objects with keys:
  title, question, columns_used, method, success_metric, expected_cost
where expected_cost is "low", "medium" or "high"."""
    plans = llm.ask_json(PLANNER_SYSTEM, user, max_tokens=2500)
    return plans if isinstance(plans, list) else plans.get("plans", [])


def choose_plan(plans: list[dict], question: str) -> dict:
    user = f"""Business question: {question}

Candidate plans:
{json.dumps(plans, indent=2)}

Pick the single plan that best answers the question within a low compute budget.
Return JSON: {{"chosen_index": 0, "why": "one sentence"}}"""
    pick = llm.ask_json(PLANNER_SYSTEM, user, max_tokens=500)
    idx = int(pick.get("chosen_index", 0))
    chosen = plans[min(idx, len(plans) - 1)]
    chosen["_why_chosen"] = pick.get("why", "")
    return chosen


def run_analysis(plan: dict, data_card: str, check_block: str, question: str,
                 sandbox, max_turns: int, feedback: str | None = None,
                 on_step=None) -> dict:
    task = f"""Business question:
{question}

The plan you are executing:
{json.dumps(plan, indent=2)}

Data profile:
{data_card}

Validity checks (already run for you -- act on these):
{check_block}

The CSV is at os.path.join(DATA_DIR, '{plan.get("_csv_name", "subscriptions.csv")}').

Do the analysis. Save every chart into figures/ for the written report.
{CUBE_CONTRACT}
When finished, respond with a single JSON object in exactly this shape and
nothing else:
{FINDINGS_SCHEMA}"""

    if feedback:
            task += f"\n\nA reviewer rejected your previous attempt. Fix this:\n{feedback}"

    result = llm.agent_loop(ANALYST_SYSTEM, task, sandbox,
                            max_turns=max_turns, on_step=on_step)
    try:
        result["findings"] = llm._parse_json(result["final_text"])
    except Exception as exc:
        result["findings"] = None
        result["parse_error"] = str(exc)
    return result


def judge(result: dict, check_block: str, question: str) -> dict:
    transcript = "\n\n".join(
        f"--- step {s['turn']} ({'ok' if s['ok'] else 'FAILED'}): {s['purpose']}\n"
        f"CODE:\n{s['code'][:1800]}\n\nOUTPUT:\n{s['output'][:1800]}"
        for s in result["steps"][-8:]
    )
    user = f"""Business question: {question}

Validity checks that were provided to the analyst:
{check_block}

Execution transcript (last steps):
{transcript}

Findings the analyst produced:
{json.dumps(result.get("findings"), indent=2)[:6000]}

Return JSON: {{"verdict": "keep|fix|drop", "reasons": ["..."],
"required_fixes": ["..."], "unsupported_claims": ["..."]}}"""
    return llm.ask_json(JUDGE_SYSTEM, user, max_tokens=1500)
