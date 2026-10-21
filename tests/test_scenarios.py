"""End-to-end: each agent-written demo PR must get exactly the verdict the demo promises."""

import subprocess
from pathlib import Path

import pytest

from sentinel import demo, engine
from sentinel.models import PullRequestInfo, Report


@pytest.fixture(scope="module")
def reports(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Report]:
    target = tmp_path_factory.mktemp("demo") / "repo"
    out: dict[str, Report] = {}
    for sc in demo.build(target):
        subprocess.run(["git", "checkout", "-q", sc.branch], cwd=target, check=True)
        pr = PullRequestInfo(base="main", head="HEAD", title=sc.title, linked_issue=sc.issue_number)
        events = list(engine.review(target, "main", pr=pr, pr_body=sc.pr_body, issue_body=sc.issue_body, use_ai=False))
        out[sc.branch] = Report.model_validate(events[-1]["report"])
    return out


def test_clean_pr_is_ready(reports: dict[str, Report]) -> None:
    r = reports["agent/discount-codes"]
    assert r.verdict.kind == "ready", r.verdict
    assert [c.status for c in r.criteria] == ["proven", "proven", "proven"]


def test_untested_criterion_needs_human(reports: dict[str, Report]) -> None:
    r = reports["agent/shipping-estimate"]
    assert r.verdict.kind == "after_checks"
    assert not r.verdict.blockers
    assert {c.id: c.status for c in r.criteria}["AC3"] == "untested"


def test_tampered_tests_and_injection_block(reports: dict[str, Report]) -> None:
    r = reports["agent/order-search"]
    assert r.verdict.kind == "do_not_merge"
    rules = {f.rule.split(":")[0] for f in r.findings}
    assert {"B608", "test-weakened"} <= rules
    assert {c.id: c.status for c in r.criteria}["AC2"] == "not_run"  # its only test is skipped


def test_only_added_lines_are_reported(reports: dict[str, Report]) -> None:
    for r in reports.values():
        added = {(f.path, ln) for f in r.changed_files for ln in f.added_lines}
        assert all((f.path, f.line) in added for f in r.findings if f.line and f.stage != "integrity")


def test_reports_round_trip_as_json(reports: dict[str, Report], tmp_path: Path) -> None:
    for r in reports.values():
        assert Report.model_validate_json(r.model_dump_json()) == r
