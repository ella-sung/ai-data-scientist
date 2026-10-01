"""
Runs model-written Python code.

Two backends:
  - 'subprocess' (default): a separate Python process with a timeout, confined
    to a scratch working directory. Fine for a laptop you are watching.
  - 'docker': the same code inside a throwaway container with the data mounted
    read-only and networking off. Use this before leaving a run unattended.

The isolation is the point. Model-written code has bugs; some of them delete
things. Never run this against a directory you care about.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TIMEOUT = 300  # seconds per execution
MAX_OUTPUT_CHARS = 6000  # truncate before it goes back into the prompt


@dataclass
class ExecResult:
    ok: bool
    stdout: str
    stderr: str
    returncode: int

    def as_tool_result(self) -> str:
        parts = []
        if self.stdout.strip():
            parts.append(f"STDOUT:\n{self.stdout.strip()}")
        if self.stderr.strip():
            parts.append(f"STDERR:\n{self.stderr.strip()}")
        if not parts:
            parts.append("(no output)")
        text = "\n\n".join(parts)
        if len(text) > MAX_OUTPUT_CHARS:
            head = text[: MAX_OUTPUT_CHARS // 2]
            tail = text[-MAX_OUTPUT_CHARS // 2 :]
            text = f"{head}\n\n...[truncated]...\n\n{tail}"
        return text


class Sandbox:
    def __init__(self, workdir: str | Path, data_dir: str | Path,
                 backend: str = "subprocess", timeout: int = DEFAULT_TIMEOUT):
        self.workdir = Path(workdir).resolve()
        self.data_dir = Path(data_dir).resolve()
        self.backend = backend
        self.timeout = timeout
        self.workdir.mkdir(parents=True, exist_ok=True)
        (self.workdir / "figures").mkdir(exist_ok=True)

    def run(self, code: str) -> ExecResult:
        script = self.workdir / "_step.py"
        script.write_text(self._preamble() + textwrap.dedent(code))
        if self.backend == "docker":
            return self._run_docker(script)
        return self._run_subprocess(script)

    def _preamble(self) -> str:
        # Non-interactive plotting, and a stable pointer to the data.
        data_path = "/data" if self.backend == "docker" else str(self.data_dir)
        return (
            "import matplotlib\n"
            "matplotlib.use('Agg')\n"
            f"DATA_DIR = r'{data_path}'\n"
            "import os\n"
            "os.makedirs('figures', exist_ok=True)\n\n"
        )

    def _run_subprocess(self, script: Path) -> ExecResult:
        try:
            proc = subprocess.run(
                [sys.executable, script.name],
                cwd=self.workdir,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            return ExecResult(False, "", f"Timed out after {self.timeout}s.", -1)
        return ExecResult(proc.returncode == 0, proc.stdout, proc.stderr, proc.returncode)

    def _run_docker(self, script: Path) -> ExecResult:
        if not shutil.which("docker"):
            return ExecResult(False, "", "docker not found on PATH", -1)
        cmd = [
            "docker", "run", "--rm",
            "--network", "none",
            "--memory", "4g", "--cpus", "2", "--pids-limit", "256",
            "-v", f"{self.workdir}:/work",
            "-v", f"{self.data_dir}:/data:ro",
            "-w", "/work",
            "ds-agent:latest",
            "python", script.name,
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            return ExecResult(False, "", f"Timed out after {self.timeout}s.", -1)
        return ExecResult(proc.returncode == 0, proc.stdout, proc.stderr, proc.returncode)

    def artifacts(self) -> dict:
        figs = sorted(p.name for p in (self.workdir / "figures").glob("*.png"))
        return {
            "figures": figs,
            "files": sorted(p.name for p in self.workdir.glob("*") if p.is_file()),
        }
