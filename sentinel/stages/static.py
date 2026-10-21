"""Checks that read the changed code without running it.

Every tool runs on the whole changed file (so it has context) but only findings on
lines the PR *added* are reported: reviewers judge the change, not legacy code.
"""

from __future__ import annotations

import ast
import importlib
import importlib.metadata
import importlib.util
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from radon.complexity import cc_visit

from sentinel.config import Config
from sentinel.models import ChangedFile, Finding, FunctionMetric, Severity
from sentinel.proc import python


def python_sources(files: list[ChangedFile], include_tests: bool = True) -> list[ChangedFile]:
    return [f for f in files if f.path.endswith(".py") and f.status != "deleted" and (include_tests or not f.is_test)]


def _on_added_line(files: list[ChangedFile], path: str, line: int | None) -> bool:
    return any(f.path == path and line in f.added_lines for f in files)


# --- imports: hallucinated packages / APIs and undeclared dependencies --------------

def _dist_for_import() -> dict[str, list[str]]:
    return {k: [d.lower().replace("_", "-") for d in v] for k, v in importlib.metadata.packages_distributions().items()}


def _missing_attrs(module: str, names: list[str]) -> list[str]:
    try:
        mod = importlib.import_module(module)  # stdlib only — never imports code under review
    except ImportError:
        return names
    return [n for n in names if not hasattr(mod, n)]


def _check_module(name: str, line: int, path: str, cfg: Config, first_party: set[str],
                  dists: dict[str, list[str]], is_test: bool = False) -> Finding | None:
    top = name.split(".")[0]
    if top in sys.stdlib_module_names or top in first_party or top == "__future__":
        return None
    approved = {d.lower() for d in cfg.declared_dependencies + cfg.allowed_packages}
    installed_as = dists.get(top, [])
    if top.lower() in approved or any(d in approved for d in installed_as):
        return None
    if installed_as or importlib.util.find_spec(top) is not None:
        if is_test:  # test tooling (pytest, hypothesis…) is rarely in [project] dependencies
            return None
        return Finding(stage="imports", rule="undeclared-dependency", severity="medium", path=path, line=line,
                       message=f"'{top}' is imported but not declared in pyproject.toml — a new dependency needs approval.")
    return Finding(stage="imports", rule="hallucinated-package", severity="critical", path=path, line=line,
                   message=f"Package '{top}' does not exist here and is not a declared dependency — possibly "
                           "hallucinated by the agent (attackers register such names on PyPI).")


def _stdlib_aliases(tree: ast.Module) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                top = a.name.split(".")[0]
                if top in sys.stdlib_module_names:
                    aliases[a.asname or top] = a.name if a.asname else top
    return aliases


def _import_findings(node: ast.AST, f: ChangedFile, cfg: Config, first_party: set[str],
                     dists: dict[str, list[str]]) -> list[Finding]:
    path = f.path
    if isinstance(node, ast.Import):
        return [hit for a in node.names
                if (hit := _check_module(a.name, node.lineno, path, cfg, first_party, dists, f.is_test))]
    if not (isinstance(node, ast.ImportFrom) and node.module and node.level == 0):
        return []
    if hit := _check_module(node.module, node.lineno, path, cfg, first_party, dists, f.is_test):
        return [hit]
    if node.module.split(".")[0] not in sys.stdlib_module_names:
        return []
    return [
        Finding(stage="imports", rule="hallucinated-api", severity="critical", path=path, line=node.lineno,
                message=f"'{node.module}' has no '{n}' — the API does not exist.")
        for n in _missing_attrs(node.module, [a.name for a in node.names if a.name != "*"])
    ]


def imports(root: Path, files: list[ChangedFile], cfg: Config, first_party: set[str]) -> list[Finding]:
    findings: list[Finding] = []
    dists = _dist_for_import()
    for f in python_sources(files):
        try:
            tree = ast.parse((root / f.path).read_text())
        except SyntaxError as e:
            findings.append(Finding(stage="imports", rule="syntax-error", severity="critical", path=f.path,
                                    line=e.lineno, message=f"File does not parse: {e.msg}"))
            continue
        added = set(f.added_lines)
        aliases = _stdlib_aliases(tree)
        for node in ast.walk(tree):
            if getattr(node, "lineno", None) not in added:
                continue
            findings += _import_findings(node, f, cfg, first_party, dists)
            if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in aliases
                    and _missing_attrs(aliases[node.value.id], [node.attr])):
                findings.append(Finding(stage="imports", rule="hallucinated-api", severity="critical", path=f.path,
                                        line=node.lineno, message=f"'{aliases[node.value.id]}.{node.attr}' does not exist."))
    return findings


# --- lint & types --------------------------------------------------------------------

_DEFAULT_RUFF = ["--isolated", "--select", "E,W,F,B,UP,SIM,RET,PLE,PLW,ARG,PIE,N", "--line-length", "120"]


def lint(root: Path, files: list[ChangedFile], cfg: Config) -> list[Finding]:
    paths = [f.path for f in python_sources(files)]
    if not paths:
        return []
    args = ["-m", "ruff", "check", "--no-cache", "--output-format", "json", *([] if cfg.has_ruff_config else _DEFAULT_RUFF)]
    result = python(*args, *paths, cwd=root)
    findings = []
    for item in json.loads(result.stdout or "[]"):
        path = str(Path(item["filename"]).resolve().relative_to(root.resolve()))
        line = item["location"]["row"]
        if not _on_added_line(files, path, line):
            continue
        code = item.get("code") or "ruff"
        bug = code.startswith(("F", "B", "PLE"))
        findings.append(Finding(stage="lint", rule=code, severity="medium" if bug else "low", path=path, line=line,
                                message=item["message"]))
    return findings


_MYPY = re.compile(r"^(.+?):(\d+): (error|note): (.+?)(?:\s+\[([\w-]+)\])?$")


def types(root: Path, files: list[ChangedFile], cfg: Config) -> list[Finding]:
    paths = [f.path for f in python_sources(files, include_tests=False)]
    if not paths:
        return []
    with tempfile.TemporaryDirectory() as cache:
        args = ["-m", "mypy", "--no-error-summary", "--hide-error-context", "--no-color-output", "--cache-dir", cache,
                "--follow-imports", "silent", *([] if cfg.has_mypy_config else ["--strict"]), *paths]
        result = python(*args, cwd=root, pythonpath=[str(root), str(root / "src")])
    findings = []
    for line in result.stdout.splitlines():
        m = _MYPY.match(line)
        if not m or m.group(3) != "error" or not _on_added_line(files, m.group(1), int(m.group(2))):
            continue
        rule = m.group(5) or "mypy"
        sev: Severity = "low" if rule in ("no-untyped-def", "type-arg", "no-untyped-call") else "medium"
        findings.append(Finding(stage="types", rule=rule, severity=sev, path=m.group(1), line=int(m.group(2)),
                                message=m.group(4)))
    return findings


# --- complexity -----------------------------------------------------------------------

def _max_depth(node: ast.AST, depth: int = 0) -> int:
    nested = (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.Match, ast.AsyncFor, ast.AsyncWith)
    return max([depth, *(_max_depth(c, depth + 1 if isinstance(c, nested) else depth) for c in ast.iter_child_nodes(node))])


def _limit_findings(fm: FunctionMetric, cfg: Config) -> list[Finding]:
    out = []
    if fm.complexity > cfg.max_complexity:
        out.append(Finding(stage="complexity", rule="cyclomatic", path=fm.path, line=fm.line,
                           severity="high" if fm.complexity > 2 * cfg.max_complexity else "medium",
                           message=f"{fm.name} has cyclomatic complexity {fm.complexity} (limit {cfg.max_complexity})."))
    if fm.max_depth > cfg.max_depth:
        out.append(Finding(stage="complexity", rule="nesting", severity="medium", path=fm.path, line=fm.line,
                           message=f"{fm.name} nests {fm.max_depth} levels deep (limit {cfg.max_depth})."))
    if fm.length > cfg.max_function_lines:
        out.append(Finding(stage="complexity", rule="function-length", severity="low", path=fm.path, line=fm.line,
                           message=f"{fm.name} is {fm.length} lines (limit {cfg.max_function_lines})."))
    return out


def complexity(root: Path, files: list[ChangedFile], cfg: Config) -> tuple[list[Finding], list[FunctionMetric]]:
    """Metrics for every function the PR touched (any added line inside it)."""
    findings: list[Finding] = []
    metrics: list[FunctionMetric] = []
    for f in python_sources(files, include_tests=False):
        source = (root / f.path).read_text()
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        defs = {(n.name, n.lineno): n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}
        blocks: list[Any] = []
        for b in cc_visit(source):
            blocks.extend(b.methods if hasattr(b, "methods") else [b])
        for b in blocks:
            node = defs.get((b.name, b.lineno))
            if node is None:
                continue
            end = node.end_lineno or b.lineno
            if not any(b.lineno <= ln <= end for ln in f.added_lines):
                continue
            fm = FunctionMetric(path=f.path, name=b.fullname, line=b.lineno, complexity=b.complexity,
                                length=end - b.lineno + 1, max_depth=_max_depth(node))
            metrics.append(fm)
            findings += _limit_findings(fm, cfg)
    return findings, metrics


# --- security --------------------------------------------------------------------------

_ESCALATE: dict[str, Severity] = {
    "B102": "critical", "B307": "critical",                    # exec / eval
    "B608": "high", "B602": "high", "B605": "high",            # SQL / shell injection
    "B301": "high", "B324": "high",                            # pickle, md5/sha1
    "B105": "high", "B106": "high", "B107": "high",            # hard-coded passwords
    "B311": "medium",                                          # random for security
}


def security(root: Path, files: list[ChangedFile]) -> list[Finding]:
    paths = [f.path for f in python_sources(files, include_tests=False)]
    if not paths:
        return []
    result = python("-m", "bandit", "-q", "-f", "json", *paths, cwd=root)
    findings = []
    for r in json.loads(result.stdout or "{}").get("results", []):
        path = r["filename"].removeprefix("./")
        if not _on_added_line(files, path, r["line_number"]):
            continue
        sev: Severity = _ESCALATE.get(r["test_id"], r["issue_severity"].lower())
        findings.append(Finding(stage="security", rule=f"{r['test_id']}:{r['test_name']}", severity=sev, path=path,
                                line=r["line_number"], message=r["issue_text"]))
    return findings
