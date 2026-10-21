"""Running tools as subprocesses with timeouts and a scrubbed environment."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Lets the target repo's pytest load `sentinel.pytest_plugin` even when Sentinel is not pip-installed.
_SENTINEL_HOME = str(Path(__file__).resolve().parent.parent)


@dataclass
class ToolResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


def python(*args: str, cwd: Path, timeout: float = 120, env: dict[str, str] | None = None,
           pythonpath: list[str] | None = None) -> ToolResult:
    """Runs `python <args>` with the interpreter Sentinel itself runs on.

    Only PATH/HOME-style basics are passed through: API keys and CI tokens from the
    host never reach code under review.
    """
    keep = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT")
    clean = {k: v for k, v in os.environ.items() if k in keep}
    clean.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"})
    clean["PYTHONPATH"] = os.pathsep.join([*(pythonpath or []), _SENTINEL_HOME])
    clean.update(env or {})
    try:
        proc = subprocess.run([sys.executable, *args], cwd=cwd, env=clean, capture_output=True, text=True,
                              timeout=timeout, check=False)
        return ToolResult(proc.returncode, proc.stdout, proc.stderr)
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        return ToolResult(-1, out, f"timed out after {timeout:.0f}s", timed_out=True)
