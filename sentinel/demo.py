"""Builds the demo service as a real git repository: `main` plus one branch per agent-written PR.

Used by the end-to-end tests, by `sentinel demo` for a local walkthrough, and to publish
the public demo repository.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent.parent / "demo"


@dataclass
class Scenario:
    name: str
    branch: str
    title: str
    pr_body: str
    issue_title: str
    issue_body: str
    issue_number: int


def scenarios() -> list[Scenario]:
    out = []
    for i, d in enumerate(sorted((DEMO_DIR / "scenarios").iterdir()), start=1):
        pr, issue = (d / "pr.md").read_text(), (d / "issue.md").read_text()
        out.append(Scenario(
            name=d.name, branch=f"agent/{re.sub(r'^\d+-', '', d.name)}",
            title=pr.splitlines()[0].lstrip("# ").strip(), pr_body=pr.split("\n", 1)[1].strip(),
            issue_title=issue.splitlines()[0].lstrip("# ").strip(), issue_body=issue.split("\n", 1)[1].strip(),
            issue_number=i,
        ))
    return out


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def build(target: Path) -> list[Scenario]:
    """Creates `target` as a git repo with the base service on `main` and each scenario on its own branch."""
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(DEMO_DIR / "service", target, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    _git(target, "init", "-q", "-b", "main")
    _git(target, "config", "user.name", "Demo Team")
    _git(target, "config", "user.email", "demo@example.com")
    _git(target, "add", "-A")
    _git(target, "commit", "-q", "-m", "Order pricing service")

    found = scenarios()
    for sc in found:
        _git(target, "checkout", "-q", "-b", sc.branch, "main")
        shutil.copytree(DEMO_DIR / "scenarios" / sc.name / "files", target, dirs_exist_ok=True)
        _git(target, "add", "-A")
        _git(target, "-c", "user.name=coding-agent", "-c", "user.email=agent@example.com", "commit", "-q", "-m", sc.title)
    _git(target, "checkout", "-q", "main")
    return found
