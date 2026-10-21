"""Checks that run the code: the repo's own test suite, coverage of changed lines, mutation testing on changed lines.

Everything runs in a throwaway copy of the repository, never in the developer's checkout.
"""

from __future__ import annotations

import ast
import json
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from sentinel.config import Config
from sentinel.models import ChangedFile, DiffCoverage, Mutant, TestResult
from sentinel.proc import python
from sentinel.stages.static import python_sources

_IGNORE = shutil.ignore_patterns(".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache",
                                 ".pytest_cache", ".ruff_cache", ".sentinel", "dist", "build", "*.egg-info")


def sandbox_copy(root: Path) -> Path:
    target = Path(tempfile.mkdtemp(prefix="sentinel-")) / "repo"
    shutil.copytree(root, target, ignore=_IGNORE, symlinks=True)
    return target


def _paths(root: Path) -> list[str]:
    return [str(root), str(root / "src")]


@dataclass
class TestRun:
    results: list[TestResult]
    coverage: DiffCoverage | None
    error: str | None


def run_tests(sandbox: Path, files: list[ChangedFile]) -> TestRun:
    results_file = sandbox / ".sentinel-results.json"
    run = python("-m", "coverage", "run", "--branch", "--source=.", "--data-file=.sentinel-coverage",
                 "-m", "pytest", "-q", "-p", "sentinel.pytest_plugin", "-p", "no:cacheprovider",
                 cwd=sandbox, timeout=600, env={"SENTINEL_RESULTS": str(results_file)}, pythonpath=_paths(sandbox))
    if run.timed_out:
        return TestRun([], None, "The test suite exceeded 10 minutes and was stopped.")
    results = [TestResult(**r) for r in json.loads(results_file.read_text())] if results_file.exists() else []
    error = None
    if not results:
        error = (run.stdout + run.stderr)[-2000:] or "No tests were collected."
    elif run.returncode not in (0, 1):  # 1 = some tests failed (already in results); anything else = crash
        error = (run.stdout + run.stderr)[-2000:]
    return TestRun(results, _diff_coverage(sandbox, files), error)


def _diff_coverage(sandbox: Path, files: list[ChangedFile]) -> DiffCoverage | None:
    out = sandbox / ".sentinel-coverage.json"
    python("-m", "coverage", "json", "--data-file=.sentinel-coverage", "-o", str(out), "-q", cwd=sandbox)
    if not out.exists():
        return None
    data = json.loads(out.read_text())["files"]
    covered = total = 0
    uncovered: dict[str, list[int]] = {}
    for f in python_sources(files, include_tests=False):
        entry = data.get(f.path)
        if entry is None:
            continue
        executable = set(entry["executed_lines"]) | set(entry["missing_lines"])
        changed = [ln for ln in f.added_lines if ln in executable]
        missed = [ln for ln in changed if ln in set(entry["missing_lines"])]
        total += len(changed)
        covered += len(changed) - len(missed)
        if missed:
            uncovered[f.path] = missed
    return DiffCoverage(covered=covered, total=total, percent=round(100 * covered / total, 1) if total else None,
                        uncovered=uncovered)


# --- mutation testing on changed lines -------------------------------------------------
# "Who tests the tests?" Plant a small bug on a line the PR added; good tests fail ("kill" it).

_COMPARE: dict[type[ast.cmpop], type[ast.cmpop]] = {
    ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.In: ast.NotIn, ast.NotIn: ast.In,
}
_BINOP: dict[type[ast.operator], type[ast.operator]] = {
    ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult, ast.FloorDiv: ast.Mult,
}
_SYM = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!=", ast.In: "in",
        ast.NotIn: "not in", ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.FloorDiv: "//"}


def _describe(node: ast.AST) -> str | None:
    if isinstance(node, ast.Compare) and type(node.ops[0]) in _COMPARE:
        return f"`{_SYM[type(node.ops[0])]}` → `{_SYM[_COMPARE[type(node.ops[0])]]}`"
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOP:
        return f"`{_SYM[type(node.op)]}` → `{_SYM[_BINOP[type(node.op)]]}`"
    if isinstance(node, ast.BoolOp):
        return "`and` → `or`" if isinstance(node.op, ast.And) else "`or` → `and`"
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return f"`{node.value}` → `{not node.value}`"
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return f"`{node.value}` → `{node.value + 1}`"
    if isinstance(node, ast.Return) and node.value is not None and not (
            isinstance(node.value, ast.Constant) and node.value.value is None):
        return "`return …` → `return None`"
    return None


def _mutate(source: str, index: int) -> str:
    tree = ast.parse(source)
    node = list(ast.walk(tree))[index]
    if isinstance(node, ast.Compare):
        node.ops[0] = _COMPARE[type(node.ops[0])]()
    elif isinstance(node, ast.BinOp):
        node.op = _BINOP[type(node.op)]()
    elif isinstance(node, ast.BoolOp):
        node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
    elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
        node.value = not node.value
    elif isinstance(node, ast.Constant) and isinstance(node.value, int):
        node.value += 1
    elif isinstance(node, ast.Return):
        node.value = ast.Constant(value=None)
    return ast.unparse(tree)


def _docstring_lines(tree: ast.Module) -> set[int]:
    lines: set[int] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str):
            lines.update(range(n.lineno, (n.end_lineno or n.lineno) + 1))
    return lines


def mutation(sandbox: Path, files: list[ChangedFile], cfg: Config) -> list[Mutant]:
    candidates: list[tuple[str, int, int, str]] = []  # path, node index, line, description
    for f in python_sources(files, include_tests=False):
        source = (sandbox / f.path).read_text()
        tree = ast.parse(source)
        skip, added = _docstring_lines(tree), set(f.added_lines)
        for i, node in enumerate(ast.walk(tree)):
            line = getattr(node, "lineno", 0)
            desc = _describe(node)
            if desc and line in added and line not in skip:
                candidates.append((f.path, i, line, desc))
    if len(candidates) > cfg.max_mutants:  # sample evenly so big PRs stay fast
        step = len(candidates) / cfg.max_mutants
        candidates = [candidates[int(i * step)] for i in range(cfg.max_mutants)]

    def run_one(mid: int, path: str, index: int, line: int, desc: str) -> Mutant:
        copy = Path(tempfile.mkdtemp(prefix="sentinel-mutant-")) / "repo"
        shutil.copytree(sandbox, copy, ignore=_IGNORE, symlinks=True)
        try:
            (copy / path).write_text(_mutate((copy / path).read_text(), index))
            # Load the plugin here too: repos using --strict-markers would otherwise error on @req
            # and every mutant would look "killed".
            r = python("-m", "pytest", "-x", "-q", "-p", "sentinel.pytest_plugin", "-p", "no:cacheprovider",
                       cwd=copy, timeout=120,
                       pythonpath=_paths(copy))
            killed = r.returncode != 0
        finally:
            shutil.rmtree(copy.parent, ignore_errors=True)
        return Mutant(id=mid, path=path, line=line, description=desc, killed=killed)

    with ThreadPoolExecutor(max_workers=6) as pool:
        return list(pool.map(lambda c: run_one(*c), [(i + 1, *c) for i, c in enumerate(candidates)]))
