"""
Everything that talks to the model.

Three entry points:
  ask()        - one call, get text back
  ask_json()   - one call, get a parsed dict back
  agent_loop() - the actual agent: model asks to run code, we run it, we hand
                 back the output, repeat until it stops asking or hits the cap

agent_loop is the whole idea of this project in about forty lines. Everything
else in the repo is scaffolding around it.
"""

from __future__ import annotations

import json
import os
import re

import anthropic

MODEL = os.environ.get("DS_AGENT_MODEL", "claude-sonnet-5")

_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Put it in a .env file and call "
                "load_dotenv(), or export it in your shell."
            )
        _client = anthropic.Anthropic(api_key=key)
    return _client


RUN_PYTHON_TOOL = {
    "name": "run_python",
    "description": (
        "Execute Python in the analysis working directory and return stdout and "
        "stderr. State is NOT preserved between calls, so each snippet must be "
        "self-contained: re-import and re-load the data every time. "
        "The variable DATA_DIR is pre-defined and points at the folder holding "
        "the CSV. Save any chart as a PNG into the 'figures/' subfolder. "
        "pandas, numpy, scikit-learn and matplotlib are available."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python source to execute."},
            "purpose": {"type": "string", "description": "One line: why you are running this."},
        },
        "required": ["code"],
    },
}


def ask(system: str, user: str, max_tokens: int = 2000) -> str:
    msg = client().messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in msg.content if b.type == "text")


def ask_json(system: str, user: str, max_tokens: int = 2000) -> dict | list:
    """Same as ask(), but insists on JSON and parses it."""
    raw = ask(
        system + "\n\nRespond with valid JSON only. No prose, no markdown fences.",
        user,
        max_tokens,
    )
    return _parse_json(raw)


def _parse_json(raw: str):
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # last resort: grab the outermost brace/bracket pair
        m = re.search(r"[\{\[].*[\}\]]", text, re.S)
        if not m:
            raise ValueError(f"Model did not return JSON:\n{raw[:500]}")
        return json.loads(m.group(0))


def agent_loop(system: str, task: str, sandbox, max_turns: int = 25,
               on_step=None) -> dict:
    """
    Let the model work until it stops calling tools or runs out of turns.

    Returns the final text plus a transcript of every code block it ran, which
    is what the judge and the report generator read afterwards.
    """
    messages = [{"role": "user", "content": task}]
    steps: list[dict] = []

    for turn in range(max_turns):
        msg = client().messages.create(
            model=MODEL,
            max_tokens=8000,
            system=system,
            tools=[RUN_PYTHON_TOOL],
            messages=messages,
        )
        messages.append({"role": "assistant", "content": msg.content})

        tool_uses = [b for b in msg.content if b.type == "tool_use"]
        if not tool_uses:
            final = "".join(b.text for b in msg.content if b.type == "text")
            return {"final_text": final, "steps": steps, "turns_used": turn + 1,
                    "hit_cap": False}

        results = []
        for block in tool_uses:
            code = block.input.get("code", "")
            purpose = block.input.get("purpose", "")
            outcome = sandbox.run(code)
            steps.append({
                "turn": turn + 1,
                "purpose": purpose,
                "code": code,
                "ok": outcome.ok,
                "output": outcome.as_tool_result(),
            })
            if on_step:
                on_step(steps[-1])
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": outcome.as_tool_result(),
                "is_error": not outcome.ok,
            })
        messages.append({"role": "user", "content": results})

    return {"final_text": "(turn cap reached before the agent finished)",
            "steps": steps, "turns_used": max_turns, "hit_cap": True}
