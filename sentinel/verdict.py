"""Turns evidence into a merge recommendation for the human reviewer.

    ⛔ do_not_merge  — hard evidence the PR is wrong or the evidence was tampered with
    🟡 after_checks  — nothing is proven wrong, but something needs a human look
    ✅ ready         — every acceptance criterion proven, nothing flagged

Tools and tests decide ⛔ and ✅. The AI reviewer can only add 🟡 items.
"""

from __future__ import annotations

from sentinel.config import Config
from sentinel.models import (
    ACTrace,
    DiffCoverage,
    Finding,
    FunctionMetric,
    Mutant,
    Scores,
    Severity,
    TestResult,
    Verdict,
)

_PENALTY: dict[Severity, int] = {"critical": 45, "high": 25, "medium": 8, "low": 2, "info": 0}
WEIGHTS = {"requirements": 0.25, "correctness": 0.2, "security": 0.2, "test_strength": 0.15,
           "maintainability": 0.1, "integrity": 0.1}


def _clamp(n: float) -> int:
    return max(0, min(100, round(n)))


def _penalty(findings: list[Finding], stages: set[str]) -> int:
    return _clamp(100 - sum(_PENALTY[f.severity] for f in findings if f.stage in stages))


def failing_tests(tests: list[TestResult]) -> list[TestResult]:
    return [t for t in tests if not t.passed and t.message != "skipped"]


def mutation_score(mutants: list[Mutant]) -> float | None:
    return round(100 * sum(m.killed for m in mutants) / len(mutants), 1) if mutants else None


def score(criteria: list[ACTrace], findings: list[Finding], tests: list[TestResult], test_error: str | None,
          coverage: DiffCoverage | None, mutants: list[Mutant]) -> tuple[Scores, int]:
    points = {"proven": 1.0, "disputed": 0.5, "untested": 0.0, "failing": 0.0, "not_run": 0.0}
    ran = [t for t in tests if t.message != "skipped"]
    strength = [p for p in (coverage.percent if coverage else None, mutation_score(mutants)) if p is not None]
    scores = Scores(
        requirements=_clamp(100 * sum(points[c.status] for c in criteria) / len(criteria)) if criteria else 50,
        correctness=0 if test_error or not ran else _clamp(100 * sum(t.passed for t in ran) / len(ran)),
        security=_penalty(findings, {"security", "imports"}),
        test_strength=_clamp(sum(strength) / len(strength)) if strength else 50,
        maintainability=_penalty(findings, {"complexity", "types", "lint"}),
        integrity=_penalty(findings, {"integrity"}),
    )
    overall = _clamp(sum(getattr(scores, k) * w for k, w in WEIGHTS.items()))
    return scores, overall


def _blockers(criteria: list[ACTrace], findings: list[Finding], tests: list[TestResult],
              test_error: str | None) -> list[str]:
    out: list[str] = []
    if test_error:
        out.append("The test suite did not run cleanly — nothing it says can be trusted yet.")
    failing = failing_tests(tests)
    if failing:
        out.append(f"{len(failing)} test(s) failing: " + ", ".join(f"`{t.nodeid.split('::')[-1]}`" for t in failing[:4]))
    for c in criteria:
        if c.status == "failing":
            out.append(f"{c.id} is not met: {c.evidence}")
        elif c.status == "not_run":
            out.append(f"{c.id} is not proven: {c.evidence}")
    severe = [f for f in findings if f.source == "tool" and f.severity in ("critical", "high")
              and f.stage in ("security", "imports", "integrity")]
    out += [f"{f.message} (`{f.path}:{f.line}`)" if f.line else f"{f.message} (`{f.path}`)" for f in severe]
    return out


def _checks(criteria: list[ACTrace], findings: list[Finding], coverage: DiffCoverage | None,
            mutants: list[Mutant], cfg: Config) -> list[str]:
    out: list[str] = []
    if not criteria:
        out.append("No acceptance criteria found. Link an issue (`Closes #12`) that lists `AC1: …` items.")
    out += [f"{c.id} has no test proving it: “{c.text}”" for c in criteria if c.status == "untested"]
    out += [f"{c.id}: tests pass, but the AI reviewer doubts it is fully implemented." for c in criteria
            if c.status == "disputed"]
    if coverage and coverage.percent is not None and coverage.percent < cfg.min_diff_coverage:
        out.append(f"Only {coverage.percent}% of changed lines are covered by tests (team minimum {cfg.min_diff_coverage:.0f}%).")
    ms = mutation_score(mutants)
    if ms is not None and ms < cfg.min_mutation_score:
        survived = len([m for m in mutants if not m.killed])
        out.append(f"Tests caught {ms}% of planted bugs (minimum {cfg.min_mutation_score:.0f}%) — {survived} would slip through.")
    tool = [f for f in findings if f.source == "tool"]
    out += [f"{f.message} (`{f.path}:{f.line}`)" for f in tool
            if f.stage == "complexity" and f.severity in ("medium", "high")]
    for stage, label in (("types", "type error"), ("lint", "likely bug flagged by ruff")):
        n = len([f for f in tool if f.stage == stage and f.severity == "medium"])
        if n:
            out.append(f"{n} {label}{'s' if n > 1 else ''} on changed lines.")
    out += [f.message + (f" (`{f.path}:{f.line}`)" if f.line else f" (`{f.path}`)") for f in tool
            if f.stage in ("integrity", "imports", "security") and f.severity == "medium"]
    ai = [f for f in findings if f.source == "ai"]
    if ai:
        out.append(f"The AI reviewer raised {len(ai)} point(s) on specific lines — see the inline comments.")
    return out


def decide(criteria: list[ACTrace], findings: list[Finding], tests: list[TestResult], test_error: str | None,
           coverage: DiffCoverage | None, mutants: list[Mutant], functions: list[FunctionMetric], cfg: Config,
           ai_focus: list[str]) -> Verdict:
    blockers = _blockers(criteria, findings, tests, test_error)
    checks = _checks(criteria, findings, coverage, mutants, cfg)

    human = [*checks]
    for fm in sorted((f for f in functions if f.complexity >= 5), key=lambda f: -f.complexity)[:2]:
        human.append(f"Read `{fm.name}` in `{fm.path}:{fm.line}` — one of the most complex changes (complexity {fm.complexity}).")
    human += ai_focus
    human.append("Design: does the change fit the architecture, naming and boundaries of this codebase? Tools cannot judge this.")

    if blockers:
        return Verdict(kind="do_not_merge", headline="Do not merge", blockers=blockers, checks=checks, human_review=human)
    if checks:
        return Verdict(kind="after_checks", headline="Merge after checks", blockers=[], checks=checks, human_review=human)
    return Verdict(kind="ready", headline="Ready to merge", blockers=[], checks=[], human_review=human)
