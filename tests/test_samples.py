"""End-to-end: every demo scenario must behave exactly as the demo claims."""

import pytest

from sentinel.models import Report, RunRequest
from sentinel.pipeline import evaluate
from sentinel.samples import SAMPLES


def _report(sample_id: str, code: str) -> Report:
    s = SAMPLES[sample_id]
    events = list(evaluate(code, RunRequest(spec=s.spec, tests=s.tests, code=code)))
    return Report.model_validate(events[-1]["report"])


@pytest.mark.parametrize("sample_id", sorted(SAMPLES))
def test_ai_first_draft_is_blocked(sample_id: str) -> None:
    report = _report(sample_id, SAMPLES[sample_id].generated)
    assert not report.gate.passed
    assert report.gate.repairable


@pytest.mark.parametrize("sample_id", ["signup", "rate-limiter"])
def test_repaired_code_passes(sample_id: str) -> None:
    report = _report(sample_id, SAMPLES[sample_id].repaired)
    assert report.gate.passed, report.gate.blockers
    assert report.gate.overall >= 95


def test_untested_requirement_escalates_even_when_code_is_clean() -> None:
    report = _report("sales-report", SAMPLES["sales-report"].repaired)
    assert not report.gate.passed
    assert not report.gate.repairable
    assert [r.id for r in report.requirements if r.status == "untested"] == ["R5"]


def test_signup_draft_findings() -> None:
    report = _report("signup", SAMPLES["signup"].generated)
    rules = {i.rule.split(":")[0] for i in report.issues}
    assert {"B608", "B324"} <= rules  # SQL injection + MD5


def test_sales_draft_hallucinated_api_and_eval() -> None:
    report = _report("sales-report", SAMPLES["sales-report"].generated)
    rules = {i.rule.split(":")[0] for i in report.issues}
    assert {"hallucinated-api", "B307"} <= rules
