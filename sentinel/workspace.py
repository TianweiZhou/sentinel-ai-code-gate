"""An isolated temp directory holding the candidate code and its tests.

Every tool runs as a separate process inside this directory with a timeout.
This is process isolation, not a security boundary — in production the same
commands run inside a locked-down container (no network, read-only FS).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

SOLUTION = "solution.py"
TESTS = "test_solution.py"

# Registers the `req` marker and writes a machine-readable result per test,
# including which requirement(s) each test verifies.
CONFTEST = '''
import json, time
import pytest

_results = []

def pytest_configure(config):
    config.addinivalue_line("markers", "req(*ids): requirement ids this test verifies")

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" or (report.when == "setup" and report.failed):
        reqs = [a for m in item.iter_markers("req") for a in m.args]
        message = None
        if report.failed:
            message = getattr(report.longrepr, "reprcrash", None)
            message = message.message if message else str(report.longrepr)[-400:]
        _results.append({
            "name": item.name, "requirement_ids": reqs, "passed": report.passed,
            "message": message, "duration_ms": report.duration * 1000,
        })

def pytest_sessionfinish(session):
    with open("sentinel_results.json", "w") as f:
        json.dump(_results, f)
'''


@dataclass
class ToolResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


class Workspace:
    def __init__(self, code: str, tests: str) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix="sentinel-"))
        self.write(code, tests)

    def write(self, code: str, tests: str) -> None:
        (self.dir / SOLUTION).write_text(code)
        (self.dir / TESTS).write_text(tests)
        (self.dir / "conftest.py").write_text(CONFTEST)

    @property
    def solution(self) -> Path:
        return self.dir / SOLUTION

    def run(self, *args: str, timeout: float = 60, cwd: Path | None = None) -> ToolResult:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            # No API keys or other secrets from the host reach the candidate code.
        }
        try:
            proc = subprocess.run(
                [sys.executable, *args], check=False, cwd=cwd or self.dir, env=env,
                capture_output=True, text=True, timeout=timeout,
            )
            return ToolResult(proc.returncode, proc.stdout, proc.stderr)
        except subprocess.TimeoutExpired as e:
            out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            return ToolResult(-1, out, "timed out", timed_out=True)

    def clone_with(self, code: str) -> Path:
        """A sibling directory with the same tests but different code (used for mutants)."""
        target = Path(tempfile.mkdtemp(prefix="sentinel-mutant-"))
        for name in (TESTS, "conftest.py"):
            shutil.copy(self.dir / name, target / name)
        (target / SOLUTION).write_text(code)
        return target

    def cleanup(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)
