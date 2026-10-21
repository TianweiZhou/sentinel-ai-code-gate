"""Stages that execute the code: tests, coverage and mutation testing."""

from __future__ import annotations

import ast
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from sentinel.models import Coverage, Mutant, TestResult
from sentinel.workspace import SOLUTION, TESTS, Workspace


@dataclass
class TestRun:
    results: list[TestResult]
    coverage: Coverage | None
    load_error: str | None


def run_tests(ws: Workspace) -> TestRun:
    run = ws.run("-m", "coverage", "run", "--branch", "--source=solution", "-m", "pytest",
                 "-q", "-p", "no:cacheprovider", "--timeout=5", TESTS, timeout=90)
    results_file = ws.dir / "sentinel_results.json"
    if run.timed_out:
        return TestRun([], None, "Test run exceeded 90s and was killed.")
    if not results_file.exists():
        return TestRun([], None, (run.stdout + run.stderr)[-1500:] or "pytest produced no results.")

    results = [TestResult(**r) for r in json.loads(results_file.read_text())]
    load_error = None
    if not results:
        load_error = (run.stdout + run.stderr)[-1500:] or "No tests were collected."

    ws.run("-m", "coverage", "json", "-o", "coverage.json", "-q")
    cov = None
    cov_file = ws.dir / "coverage.json"
    if cov_file.exists():
        data = json.loads(cov_file.read_text())
        f = data["files"].get(SOLUTION)
        if f:
            s = f["summary"]
            branches = s.get("num_branches", 0)
            cov = Coverage(
                line_percent=round(100 * s["covered_lines"] / max(s["num_statements"], 1), 1),
                branch_percent=round(100 * s["covered_branches"] / branches, 1) if branches else None,
                missing_lines=f["missing_lines"],
            )
    return TestRun(results, cov, load_error)


# --- mutation testing ----------------------------------------------------------
# "Who tests the tests?" We plant small bugs in the code. A good test suite fails
# for each one ("kills" the mutant). Surviving mutants show behaviour nobody checks.

_COMPARE_SWAP: dict[type[ast.cmpop], type[ast.cmpop]] = {
    ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.In: ast.NotIn, ast.NotIn: ast.In,
}
_BINOP_SWAP: dict[type[ast.operator], type[ast.operator]] = {
    ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult, ast.FloorDiv: ast.Mult,
}
_SYMBOL = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!=",
           ast.In: "in", ast.NotIn: "not in", ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
           ast.FloorDiv: "//", ast.And: "and", ast.Or: "or"}


def _mutation_points(tree: ast.Module) -> list[tuple[int, str]]:
    """(node index in ast.walk order, description) for every mutable spot."""
    points = []
    for i, node in enumerate(ast.walk(tree)):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Compare) and type(node.ops[0]) in _COMPARE_SWAP:
            a, b = type(node.ops[0]), _COMPARE_SWAP[type(node.ops[0])]
            points.append((i, f"line {line}: `{_SYMBOL[a]}` → `{_SYMBOL[b]}`"))
        elif isinstance(node, ast.BinOp) and type(node.op) in _BINOP_SWAP:
            a2, b2 = type(node.op), _BINOP_SWAP[type(node.op)]
            points.append((i, f"line {line}: `{_SYMBOL[a2]}` → `{_SYMBOL[b2]}`"))
        elif isinstance(node, ast.BoolOp):
            points.append((i, f"line {line}: `{_SYMBOL[type(node.op)]}` → `{'or' if isinstance(node.op, ast.And) else 'and'}`"))
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            points.append((i, f"line {line}: `{node.value}` → `{not node.value}`"))
        elif isinstance(node, ast.Constant) and type(node.value) is int and line:
            points.append((i, f"line {line}: `{node.value}` → `{node.value + 1}`"))
        elif isinstance(node, ast.Return) and node.value is not None and not (
                isinstance(node.value, ast.Constant) and node.value.value is None):
            points.append((i, f"line {line}: `return …` → `return None`"))
    return points


def _apply(code: str, index: int) -> str:
    tree = ast.parse(code)
    node = list(ast.walk(tree))[index]
    if isinstance(node, ast.Compare):
        node.ops[0] = _COMPARE_SWAP[type(node.ops[0])]()
    elif isinstance(node, ast.BinOp):
        node.op = _BINOP_SWAP[type(node.op)]()
    elif isinstance(node, ast.BoolOp):
        node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
    elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
        node.value = not node.value
    elif isinstance(node, ast.Constant) and isinstance(node.value, int):
        node.value = node.value + 1
    elif isinstance(node, ast.Return):
        node.value = ast.Constant(value=None)
    return ast.unparse(tree)


def _docstring_lines(tree: ast.Module) -> set[int]:
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            lines.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return lines


def mutation(ws: Workspace, code: str, max_mutants: int = 24) -> list[Mutant]:
    tree = ast.parse(code)
    skip = _docstring_lines(tree)
    points = [p for p in _mutation_points(tree) if int(p[1].split(":")[0].removeprefix("line ")) not in skip]
    if len(points) > max_mutants:  # sample evenly across the file so the run stays fast
        step = len(points) / max_mutants
        points = [points[int(i * step)] for i in range(max_mutants)]

    def run_one(mid: int, index: int, description: str) -> Mutant:
        line = int(description.split(":")[0].removeprefix("line "))
        target = ws.clone_with(_apply(code, index))
        try:
            r = ws.run("-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", "--timeout=3", TESTS,
                       timeout=30, cwd=target)
            killed = r.returncode != 0  # any failure, error or timeout means the tests noticed
        finally:
            shutil.rmtree(target, ignore_errors=True)
        return Mutant(id=mid, line=line, description=description, killed=killed)

    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(lambda a: run_one(*a), [(i + 1, idx, d) for i, (idx, d) in enumerate(points)]))
