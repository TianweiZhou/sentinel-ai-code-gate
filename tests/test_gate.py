from sentinel import gate
from sentinel.models import Coverage, Issue, Mutant, RequirementTrace, TestResult
from sentinel.stages.requirements import merge_judge, parse_requirements, trace


def _passing(n: int = 3) -> list[TestResult]:
    return [TestResult(name=f"t{i}", requirement_ids=["R1"], passed=True) for i in range(n)]


def _met() -> list[RequirementTrace]:
    return [RequirementTrace(id="R1", text="x", status="met", tests=["t0"], evidence="")]


GOOD_COV = Coverage(line_percent=100, branch_percent=100, missing_lines=[])
GOOD_MUTANTS = [Mutant(id=i, line=1, description="", killed=True) for i in range(10)]


def test_one_critical_finding_blocks_an_otherwise_perfect_score() -> None:
    issues = [Issue(stage="security", rule="B608", severity="high", message="sql")]
    scores = gate.score(issues, _passing(), GOOD_COV, GOOD_MUTANTS, _met())
    decision = gate.decide(scores, issues, _passing(), None, GOOD_COV, GOOD_MUTANTS, _met())
    assert decision.overall >= gate.THRESHOLD  # the average looks fine...
    assert not decision.passed                 # ...but the hard rule wins
    assert decision.repairable


def test_clean_code_passes() -> None:
    scores = gate.score([], _passing(), GOOD_COV, GOOD_MUTANTS, _met())
    decision = gate.decide(scores, [], _passing(), None, GOOD_COV, GOOD_MUTANTS, _met())
    assert decision.passed and decision.overall == 100


def test_weak_tests_escalate_to_a_human_instead_of_the_ai() -> None:
    weak = [Mutant(id=i, line=1, description="", killed=i < 3) for i in range(10)]
    scores = gate.score([], _passing(), GOOD_COV, weak, _met())
    decision = gate.decide(scores, [], _passing(), None, GOOD_COV, weak, _met())
    assert not decision.passed
    assert not decision.repairable
    assert any("Mutation score" in e for e in decision.escalations)


def test_untested_requirement_cannot_pass() -> None:
    reqs = parse_requirements("R1: does a\nR2: does b\n")
    traces = trace(reqs, _passing(), '@pytest.mark.req("R1")')
    assert [t.status for t in traces] == ["met", "untested"]
    decision = gate.decide(gate.score([], _passing(), GOOD_COV, GOOD_MUTANTS, traces), [], _passing(),
                           None, GOOD_COV, GOOD_MUTANTS, traces)
    assert not decision.passed and decision.escalations


def test_crashed_suite_marks_linked_requirements_missing_not_untested() -> None:
    traces = trace(parse_requirements("R1: x"), [], '@pytest.mark.req("R1")')
    assert traces[0].status == "missing"


def test_llm_judge_can_only_downgrade() -> None:
    failing = [RequirementTrace(id="R1", text="x", status="missing", tests=["t"], evidence="0/1")]
    assert merge_judge(failing, {"R1": ("met", "looks right")})[0].status == "missing"
    passing = _met()
    assert merge_judge(passing, {"R1": ("partial", "misses edge case")})[0].status == "partial"
    untested = [RequirementTrace(id="R2", text="x", status="untested", tests=[], evidence="")]
    assert merge_judge(untested, {"R2": ("met", "ok")})[0].status == "partial"
