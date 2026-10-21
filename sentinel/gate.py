"""Scoring and the pass/block decision.

Two layers on purpose:
  1. A weighted score — a single number that is easy to track over time.
  2. Hard rules — a high average must never hide one serious problem.
     Perfect style cannot buy back a SQL injection.
"""

from __future__ import annotations

from sentinel.models import Coverage, Gate, Issue, Mutant, RequirementTrace, Scores, Severity, TestResult

WEIGHTS: dict[str, float] = {
    "correctness": 0.25,
    "requirements": 0.20,
    "security": 0.20,
    "test_strength": 0.15,
    "maintainability": 0.10,
    "style": 0.10,
}

THRESHOLD = 85
MIN_COVERAGE = 80.0
MIN_MUTATION_SCORE = 70.0

_PENALTY: dict[Severity, int] = {"critical": 45, "high": 25, "medium": 8, "low": 3, "info": 0}


def _clamp(n: float) -> int:
    return max(0, min(100, round(n)))


def _penalty(issues: list[Issue], *stages: str) -> int:
    return _clamp(100 - sum(_PENALTY[i.severity] for i in issues if i.stage in stages))


def mutation_score(mutants: list[Mutant]) -> float | None:
    return round(100 * sum(m.killed for m in mutants) / len(mutants), 1) if mutants else None


def score(issues: list[Issue], tests: list[TestResult], cov: Coverage | None,
          mutants: list[Mutant], reqs: list[RequirementTrace]) -> Scores:
    points = {"met": 1.0, "partial": 0.5, "untested": 0.0, "missing": 0.0}
    ms = mutation_score(mutants)
    strength_parts = [p for p in (cov.line_percent if cov else None, ms) if p is not None]
    return Scores(
        correctness=_clamp(100 * sum(t.passed for t in tests) / len(tests)) if tests else 0,
        requirements=_clamp(100 * sum(points[r.status] for r in reqs) / len(reqs)) if reqs else 0,
        security=_penalty(issues, "security", "imports"),
        test_strength=_clamp(sum(strength_parts) / len(strength_parts)) if strength_parts else 0,
        maintainability=_penalty(issues, "complexity"),
        style=_penalty(issues, "lint", "types"),
    )


def decide(scores: Scores, issues: list[Issue], tests: list[TestResult], test_load_error: str | None,
           cov: Coverage | None, mutants: list[Mutant], reqs: list[RequirementTrace]) -> Gate:
    overall = _clamp(sum(getattr(scores, k) * w for k, w in WEIGHTS.items()))
    fixable: list[str] = []      # the AI can fix these by changing the code
    escalate: list[str] = []     # a human has to act (tests/spec are the human's contract)

    if any(i.stage == "parse" for i in issues):
        fixable.append("Code does not parse.")
    halluc = [i for i in issues if i.stage == "imports" and i.severity == "critical"]
    if halluc:
        fixable.append(f"{len(halluc)} hallucinated import/API.")
    if test_load_error:
        fixable.append("Test suite could not run against the code.")
    failing = [t for t in tests if not t.passed]
    if failing:
        fixable.append(f"{len(failing)}/{len(tests)} tests failing.")
    severe = [i for i in issues if i.stage in ("security", "imports") and i.severity in ("critical", "high")
              and i not in halluc]
    if severe:
        fixable.append(f"{len(severe)} critical/high security finding(s).")
    unmet = [r.id for r in reqs if r.status in ("missing", "partial")]
    if unmet:
        fixable.append(f"Requirements not met: {', '.join(unmet)}.")

    untested = [r.id for r in reqs if r.status == "untested"]
    if untested:
        escalate.append(f"No test proves {', '.join(untested)} — a human must add one (the AI may not write its own exam).")
    if not reqs:
        escalate.append("Spec has no numbered requirements (R1, R2, …).")
    if not failing and not test_load_error and tests:
        if cov and cov.line_percent < MIN_COVERAGE:
            escalate.append(f"Line coverage {cov.line_percent}% < {MIN_COVERAGE:.0f}% — tests miss code paths.")
        ms = mutation_score(mutants)
        if ms is not None and ms < MIN_MUTATION_SCORE:
            escalate.append(f"Mutation score {ms}% < {MIN_MUTATION_SCORE:.0f}% — tests are too weak to trust a green run.")

    if overall < THRESHOLD and not fixable and not escalate:
        fixable.append(f"Overall score {overall} is below {THRESHOLD}.")

    return Gate(passed=not fixable and not escalate, overall=overall, threshold=THRESHOLD,
                blockers=fixable + escalate, repairable=bool(fixable), escalations=escalate)
