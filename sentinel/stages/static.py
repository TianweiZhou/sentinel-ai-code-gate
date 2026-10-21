"""Stages that inspect the code without running it."""

from __future__ import annotations

import ast
import importlib
import importlib.util
import json
import re
import sys
from typing import Any, cast

from radon.complexity import cc_rank, cc_visit
from radon.metrics import mi_visit

from sentinel.models import FunctionMetric, Issue, Severity
from sentinel.workspace import SOLUTION, Workspace

LIMITS = {"complexity": 8, "depth": 3, "length": 40, "params": 5}


def parse(code: str) -> list[Issue]:
    try:
        ast.parse(code)
        return []
    except SyntaxError as e:
        return [Issue(stage="parse", rule="syntax-error", severity="critical", message=str(e.msg), line=e.lineno)]


# --- imports: catch hallucinated packages and hallucinated stdlib APIs -------

def _imported_names(tree: ast.Module) -> dict[str, str]:
    """Local alias -> real module name, for `import x` / `import x as y`."""
    names: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names[alias.asname or alias.name.split(".")[0]] = alias.name if alias.asname else alias.name.split(".")[0]
    return names


def _missing_names(module: str, names: list[str]) -> list[str]:
    """Names that a stdlib module does not define (only stdlib is imported — never candidate dependencies)."""
    try:
        mod = importlib.import_module(module)
    except ImportError:
        return names
    return [n for n in names if not hasattr(mod, n)]


def imports(code: str, allowed_packages: list[str]) -> list[Issue]:
    tree = ast.parse(code)
    issues: list[Issue] = []
    stdlib = sys.stdlib_module_names

    def check_module(name: str, line: int) -> bool:
        top = name.split(".")[0]
        if top in stdlib:
            return True
        if top in allowed_packages and importlib.util.find_spec(top) is not None:
            return True
        exists = importlib.util.find_spec(top) is not None
        issues.append(Issue(
            stage="imports", rule="unapproved-dependency" if exists else "hallucinated-package",
            severity="high" if exists else "critical", line=line,
            message=(f"'{top}' is not on the approved dependency list." if exists
                     else f"Package '{top}' does not exist in this environment — possibly hallucinated "
                          "(an attacker can register that name on PyPI)."),
        ))
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                check_module(alias.name, node.lineno)
        elif (isinstance(node, ast.ImportFrom) and node.module and node.level == 0
              and check_module(node.module, node.lineno) and node.module.split(".")[0] in stdlib):
            missing = _missing_names(node.module, [a.name for a in node.names if a.name != "*"])
            issues.extend(Issue(
                stage="imports", rule="hallucinated-api", severity="critical", line=node.lineno,
                message=f"'{node.module}' has no attribute '{name}' — the API does not exist.",
            ) for name in missing)

    # `json.parse(...)`-style calls on stdlib modules that don't have that attribute.
    aliases = {k: v for k, v in _imported_names(tree).items() if v in stdlib}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in aliases:
            mod = importlib.import_module(aliases[node.value.id])
            if not hasattr(mod, node.attr):
                issues.append(Issue(
                    stage="imports", rule="hallucinated-api", severity="critical", line=node.lineno,
                    message=f"'{aliases[node.value.id]}.{node.attr}' does not exist.",
                ))
    return issues


# --- lint & types ------------------------------------------------------------

def lint(ws: Workspace) -> list[Issue]:
    # Bugs (F, B, PLE), modern idioms (UP, SIM, RET), naming (N), pycodestyle (E, W).
    result = ws.run("-m", "ruff", "check", "--isolated", "--output-format", "json",
                    "--select", "E,W,F,B,UP,SIM,RET,N,PLE,PLW,ARG,PIE", "--line-length", "120", SOLUTION)
    issues = []
    for item in json.loads(result.stdout or "[]"):
        code = item.get("code") or "ruff"
        bug_like = code.startswith(("F", "B", "PLE"))
        issues.append(Issue(stage="lint", rule=code, severity="medium" if bug_like else "low",
                            message=item["message"], line=item["location"]["row"]))
    return issues


_MYPY_LINE = re.compile(r"^solution\.py:(\d+): (error|note): (.+?)(?:\s+\[([\w-]+)\])?$")


def types(ws: Workspace) -> list[Issue]:
    result = ws.run("-m", "mypy", "--strict", "--no-error-summary", "--hide-error-context",
                    "--no-color-output", "--cache-dir", ".mypy_cache", SOLUTION)
    issues = []
    for line in result.stdout.splitlines():
        m = _MYPY_LINE.match(line)
        if m and m.group(2) == "error":
            rule = m.group(4) or "mypy"
            severity: Severity = "low" if rule in ("no-untyped-def", "type-arg", "no-untyped-call") else "medium"
            issues.append(Issue(stage="types", rule=rule, severity=severity, message=m.group(3), line=int(m.group(1))))
    return issues


# --- complexity ---------------------------------------------------------------

def _max_depth(node: ast.AST, depth: int = 0) -> int:
    nested = (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.Match, ast.AsyncFor, ast.AsyncWith)
    best = depth
    for child in ast.iter_child_nodes(node):
        best = max(best, _max_depth(child, depth + 1 if isinstance(child, nested) else depth))
    return best


def complexity(code: str) -> tuple[list[Issue], list[FunctionMetric], float]:
    tree = ast.parse(code)
    defs = {(n.name, n.lineno): n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}
    functions: list[FunctionMetric] = []
    issues: list[Issue] = []

    blocks: list[Any] = []
    for block in cc_visit(code):
        blocks.extend(block.methods if hasattr(block, "methods") else [block])

    for block in blocks:
        node = defs.get((block.name, block.lineno))
        if node is None:
            continue
        fm = FunctionMetric(
            name=block.fullname, line=block.lineno, complexity=block.complexity, rank=cc_rank(block.complexity),
            length=(node.end_lineno or node.lineno) - node.lineno + 1, max_depth=_max_depth(node),
            params=len([a for a in node.args.args if a.arg not in ("self", "cls")]) + len(node.args.kwonlyargs),
        )
        functions.append(fm)
        if fm.complexity > LIMITS["complexity"]:
            issues.append(Issue(stage="complexity", rule="cyclomatic", line=fm.line,
                                severity="high" if fm.complexity > 15 else "medium",
                                message=f"{fm.name} has cyclomatic complexity {fm.complexity} (limit {LIMITS['complexity']})."))
        if fm.max_depth > LIMITS["depth"]:
            issues.append(Issue(stage="complexity", rule="nesting", severity="medium", line=fm.line,
                                message=f"{fm.name} nests {fm.max_depth} levels deep (limit {LIMITS['depth']})."))
        if fm.length > LIMITS["length"]:
            issues.append(Issue(stage="complexity", rule="function-length", severity="low", line=fm.line,
                                message=f"{fm.name} is {fm.length} lines long (limit {LIMITS['length']})."))
        if fm.params > LIMITS["params"]:
            issues.append(Issue(stage="complexity", rule="too-many-params", severity="low", line=fm.line,
                                message=f"{fm.name} takes {fm.params} parameters (limit {LIMITS['params']})."))

    return issues, functions, round(float(mi_visit(code, multi=True)), 1)


# --- security -----------------------------------------------------------------

# Bandit rates some of these as "medium"; for code nobody has reviewed yet we are stricter.
_ESCALATE: dict[str, Severity] = {
    "B102": "critical",  # exec
    "B307": "critical",  # eval
    "B608": "high",      # SQL built from strings
    "B602": "high",      # subprocess with shell=True
    "B605": "high",      # os.system / shell
    "B301": "high",      # pickle
    "B324": "high",      # md5 / sha1
    "B105": "high", "B106": "high", "B107": "high",  # hard-coded passwords
    "B311": "medium",    # random for security
}


def security(ws: Workspace) -> list[Issue]:
    result = ws.run("-m", "bandit", "-q", "-f", "json", SOLUTION)
    data = json.loads(result.stdout or "{}")
    issues = []
    for r in data.get("results", []):
        sev = _ESCALATE.get(r["test_id"], cast(Severity, r["issue_severity"].lower()))
        issues.append(Issue(stage="security", rule=f"{r['test_id']}:{r['test_name']}", severity=sev,
                            message=r["issue_text"], line=r["line_number"]))
    return issues
