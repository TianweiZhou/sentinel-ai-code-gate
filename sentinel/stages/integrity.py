"""Can we trust the evidence? Catches the ways an agent makes CI green without fixing the problem.

Compares every changed test file before and after the PR, and scans added lines for
secrets, tool-silencing comments and changes to the quality gate itself.
"""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

from sentinel import repo
from sentinel.config import Config, _dist_name
from sentinel.models import ChangedFile, Finding

_SECRETS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key id"),
    (re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private key"),
    (re.compile(r"\b(ghp|gho|ghs|github_pat)_[A-Za-z0-9_]{20,}"), "GitHub token"),
    (re.compile(r"\bsk-(ant-)?[A-Za-z0-9_-]{20,}"), "API key"),
    (re.compile(r"(?i)\b(api[_-]?key|secret|passw(or)?d|token)\w*\s*[:=]\s*['\"][A-Za-z0-9_\-+/=]{12,}['\"]"),
     "hard-coded credential"),
]
_SUPPRESS = re.compile(r"#\s*(noqa|type:\s*ignore|nosec|pragma:\s*no\s*cover)\b")
_GATE_FILES = (".github/workflows/", "conftest.py", "pytest.ini", "setup.cfg", "tox.ini", ".coveragerc")
_GATE_SECTIONS = ("pytest", "coverage", "sentinel", "ruff", "mypy")


def _tests(source: str | None) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    if not source:
        return {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    found: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test"):
            found[node.name] = node
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for item in node.body:
                if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef) and item.name.startswith("test"):
                    found[f"{node.name}.{item.name}"] = item
    return found


_ASSERT_CALLS = {"raises", "warns", "assert_called_with", "assert_called_once_with", "assertEqual", "assertTrue",
                 "assertRaises", "assertIn", "assertFalse", "assertIsNone"}


def _assertions(fn: ast.AST) -> int:
    """`assert` statements plus pytest/unittest assertion helpers inside a test."""
    return sum(
        isinstance(n, ast.Assert)
        or (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in _ASSERT_CALLS)
        for n in ast.walk(fn)
    )


def _skipped(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    decorators = " ".join(ast.unparse(d) for d in fn.decorator_list)
    calls = any(isinstance(n, ast.Call) and ast.unparse(n.func) in ("pytest.skip", "pytest.xfail", "self.skipTest")
                for n in ast.walk(fn))
    return bool(re.search(r"\b(skip|skipif|xfail)\b", decorators)) or calls


def _test_changes(root: Path, base: str, f: ChangedFile) -> list[Finding]:
    if f.status == "deleted":
        return [Finding(stage="integrity", rule="test-file-deleted", severity="high", path=f.path,
                        message="A whole test file was deleted. Tests are the evidence; removing them needs a human.")]
    before, after = _tests(repo.show(root, base, f.path)), _tests((root / f.path).read_text())
    out: list[Finding] = []
    for name, old in before.items():
        new = after.get(name)
        if new is None:
            out.append(Finding(stage="integrity", rule="test-removed", severity="high", path=f.path, line=old.lineno,
                               message=f"Existing test `{name}` was removed."))
            continue
        if _skipped(new) and not _skipped(old):
            out.append(Finding(stage="integrity", rule="test-skipped", severity="high", path=f.path, line=new.lineno,
                               message=f"Existing test `{name}` is now skipped/xfail — a common way to turn CI green."))
        a, b = _assertions(old), _assertions(new)
        if b < a:
            out.append(Finding(stage="integrity", rule="test-weakened", severity="high", path=f.path, line=new.lineno,
                               message=f"Existing test `{name}` lost {a - b} of its {a} assertion(s)."))
    return out


def _deps(text: str | None) -> set[str]:
    if not text:
        return set()
    data = tomllib.loads(text)
    project = data.get("project", {})
    deps = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        deps.extend(extra)
    return {_dist_name(d) for d in deps}


def _changed_tool_sections(before: str | None, after: str | None) -> list[str]:
    old = tomllib.loads(before).get("tool", {}) if before else {}
    new = tomllib.loads(after).get("tool", {}) if after else {}
    return [s for s in _GATE_SECTIONS if old.get(s) != new.get(s)]


def _pyproject_changes(root: Path, base: str) -> list[Finding]:
    before, after = repo.show(root, base, "pyproject.toml"), (root / "pyproject.toml").read_text() \
        if (root / "pyproject.toml").exists() else None
    out = [Finding(stage="integrity", rule="new-dependency", severity="medium", path="pyproject.toml",
                   message=f"New dependency `{d}` — check licence, maintenance and that it is really needed.")
           for d in sorted(_deps(after) - _deps(before))]
    out += [Finding(stage="integrity", rule="gate-config-changed", severity="medium", path="pyproject.toml",
                    message=f"`[tool.{s}]` settings changed — changes to how code is checked need a human.")
            for s in _changed_tool_sections(before, after)]
    return out


def _added_line_findings(f: ChangedFile) -> list[Finding]:
    out: list[Finding] = []
    for line, text in repo.added_text(f):
        for pattern, label in _SECRETS:
            if pattern.search(text):
                out.append(Finding(stage="integrity", rule="secret", severity="critical", path=f.path, line=line,
                                   message=f"Possible {label} committed. Rotate it and load it from the environment."))
                break
        m = _SUPPRESS.search(text) if f.path.endswith(".py") else None
        if m:
            out.append(Finding(stage="integrity", rule="suppression-added", severity="medium", path=f.path, line=line,
                               message=f"`# {m.group(1)}` silences a check. Agents use this to get past tools."))
    return out


def check(root: Path, base: str, files: list[ChangedFile], cfg: Config) -> list[Finding]:
    findings: list[Finding] = []
    fork_point = repo.merge_base(root, base)  # compare with what the PR branched from, not today's base
    for f in files:
        if f.is_test and f.path.endswith(".py"):
            findings += _test_changes(root, fork_point, f)
        if f.status != "deleted":
            findings += _added_line_findings(f)
        if f.path.startswith(_GATE_FILES) or f.path.endswith(_GATE_FILES):
            findings.append(Finding(stage="integrity", rule="gate-config-changed", severity="medium", path=f.path,
                                    message="CI / test configuration changed — make sure the checks were not loosened."))
        hit = next((p for p in cfg.sensitive_paths if f.path.startswith(p)), None)
        if hit:
            findings.append(Finding(stage="integrity", rule="sensitive-path", severity="medium", path=f.path,
                                    message=f"Touches `{hit}`, which this team marks as always needing human review."))
    if any(f.path == "pyproject.toml" for f in files):
        findings += _pyproject_changes(root, fork_point)
    return findings
