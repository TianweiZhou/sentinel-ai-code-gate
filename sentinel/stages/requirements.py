"""Requirement traceability: every requirement must be proven by at least one passing test."""

from __future__ import annotations

import re

from sentinel.models import Requirement, RequirementStatus, RequirementTrace, TestResult

_REQ_LINE = re.compile(r"^\s*[-*]?\s*(R\d+)\s*[:.)-]\s*(.+)$", re.MULTILINE)


def parse_requirements(spec: str) -> list[Requirement]:
    return [Requirement(id=m.group(1), text=m.group(2).strip()) for m in _REQ_LINE.finditer(spec)]


_REQ_MARKER = re.compile(r"mark\.req\(([^)]*)\)")


def declared_in_tests(test_source: str) -> set[str]:
    """Requirement ids referenced by `@pytest.mark.req(...)`, read statically so we
    still know the linkage when the suite crashes before running."""
    return {rid for args in _REQ_MARKER.findall(test_source) for rid in re.findall(r"R\d+", args)}


def trace(requirements: list[Requirement], tests: list[TestResult], test_source: str) -> list[RequirementTrace]:
    declared = declared_in_tests(test_source)
    traces = []
    for req in requirements:
        covering = [t for t in tests if req.id in t.requirement_ids]
        passed = sum(t.passed for t in covering)
        status: RequirementStatus
        if not covering and req.id in declared:
            status, evidence = "missing", "Linked tests exist but could not run against this code."
        elif not covering:
            status, evidence = "untested", "No test is marked with this requirement."
        elif passed == len(covering):
            status, evidence = "met", f"{passed}/{len(covering)} linked tests pass."
        elif passed == 0:
            status, evidence = "missing", f"All {len(covering)} linked tests fail."
        else:
            status, evidence = "partial", f"{passed}/{len(covering)} linked tests pass."
        traces.append(RequirementTrace(id=req.id, text=req.text, status=status,
                                       tests=[t.name for t in covering], evidence=evidence))
    return traces


_RANK = {"missing": 0, "partial": 1, "met": 2}


def merge_judge(traces: list[RequirementTrace], verdicts: dict[str, tuple[str, str]]) -> list[RequirementTrace]:
    """Combine test evidence with an LLM reviewer's verdict.

    Tests are authoritative. The judge may only *downgrade* (catch something the
    tests missed) or comment on an untested requirement — capped at "partial",
    because an opinion is not proof. It can never turn a failing requirement green.
    """
    merged = []
    for t in traces:
        if t.id not in verdicts:
            merged.append(t)
            continue
        status, why = verdicts[t.id]
        if t.status == "untested":
            capped: RequirementStatus = "partial" if status == "met" else ("missing" if status == "missing" else "partial")
            merged.append(t.model_copy(update={"status": capped, "source": "llm-judge",
                                               "evidence": f"No test. Judge: {why}"}))
        elif _RANK.get(status, 2) < _RANK[t.status]:
            merged.append(t.model_copy(update={"status": status, "source": "tests+llm-judge",
                                               "evidence": f"{t.evidence} Judge disagrees: {why}"}))
        else:
            merged.append(t.model_copy(update={"source": "tests+llm-judge", "evidence": f"{t.evidence} Judge: {why}"}))
    return merged
