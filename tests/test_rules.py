"""Unit tests for the rules a senior would be asked to justify."""

from sentinel.ai_review import CriterionReview, ReviewOut, apply_to_criteria
from sentinel.config import Config
from sentinel.models import ACTrace, ChangedFile, Finding, TestResult
from sentinel.repo import _added_lines
from sentinel.stages.integrity import _added_line_findings, _assertions, _skipped, _tests
from sentinel.stages.requirements import collect, linked_issue, trace
from sentinel.verdict import decide

CFG = Config()


def _ac(status: str = "proven") -> ACTrace:
    return ACTrace(id="AC1", text="x", source="issue #1", status=status, tests=["t"], evidence="")  # type: ignore[arg-type]


def _ok() -> list[TestResult]:
    return [TestResult(nodeid="t", requirement_ids=["AC1"], passed=True)]


def test_one_critical_tool_finding_blocks() -> None:
    f = [Finding(stage="security", rule="B608", severity="high", message="sql", path="a.py", line=3)]
    assert decide([_ac()], f, _ok(), None, None, [], [], CFG, []).kind == "do_not_merge"


def test_clean_evidence_is_ready() -> None:
    assert decide([_ac()], [], _ok(), None, None, [], [], CFG, []).kind == "ready"


def test_ai_findings_can_only_escalate_never_block() -> None:
    ai = [Finding(stage="ai_review", rule="risk", severity="medium", message="may double charge", source="ai")]
    v = decide([_ac()], ai, _ok(), None, None, [], [], CFG, [])
    assert v.kind == "after_checks" and not v.blockers


def test_ai_cannot_turn_a_failing_criterion_green() -> None:
    out = ReviewOut(summary="", criteria=[CriterionReview(id="AC1", status="implemented", evidence="looks right")],
                    comments=[], human_focus=[])
    assert apply_to_criteria([_ac("failing")], out)[0].status == "failing"
    disputed = ReviewOut(summary="", criteria=[CriterionReview(id="AC1", status="partial", evidence="no edge case")],
                         comments=[], human_focus=[])
    assert apply_to_criteria([_ac("proven")], disputed)[0].status == "disputed"


def test_missing_criteria_need_a_human() -> None:
    assert decide([], [], _ok(), None, None, [], [], CFG, []).kind == "after_checks"


def test_issue_criteria_win_over_pr_description() -> None:
    acs = collect("- AC1: something weaker\n- AC9: extra", "- [ ] AC1: the real contract", 4)
    assert {a.id: a.text for a in acs} == {"AC1": "the real contract", "AC9": "extra"}
    assert linked_issue("Implements it.\n\nCloses #42") == 42


def test_skipped_and_untested_criteria() -> None:
    criteria = collect("", "- AC1: a\n- AC2: b", 1)
    tests = [TestResult(nodeid="t1", requirement_ids=["AC1"], passed=False, message="skipped")]
    assert [t.status for t in trace(criteria, tests, set())] == ["not_run", "untested"]


def test_detects_weakened_and_skipped_tests() -> None:
    before = _tests("def test_a():\n    assert 1\n    assert 2\n")
    after = _tests("import pytest\n@pytest.mark.skip(reason='flaky')\ndef test_a():\n    assert 1\n")
    assert _assertions(before["test_a"]) == 2 and _assertions(after["test_a"]) == 1
    assert _skipped(after["test_a"]) and not _skipped(before["test_a"])


def test_secrets_and_suppressions_on_added_lines() -> None:
    patch = ("@@ -1,0 +1,2 @@\n+API_KEY = 'sk-ant-abcdefghijklmnopqrstuvwxyz'\n+x = compute()  # type: ignore\n")
    f = ChangedFile(path="app.py", status="modified", added_lines=[1, 2], patch=patch)
    rules = [x.rule for x in _added_line_findings(f)]
    assert rules == ["secret", "suppression-added"]


def test_added_line_numbers_from_patch() -> None:
    patch = "@@ -3,2 +3,3 @@\n context\n+new\n context\n@@ -10 +11,0 @@\n-gone\n"
    assert _added_lines(patch) == [4]
