"""Does the PR do what was asked? Acceptance criteria from the linked issue, each traced to passing tests."""

from __future__ import annotations

import re
from pathlib import Path

from sentinel.models import AcceptanceCriterion, ACStatus, ACTrace, TestResult

_AC_LINE = re.compile(r"^\s*(?:[-*]\s*)?(?:\[[ xX]\]\s*)?\**(AC-?\d+)\**\s*[:.)-]\s*(.+?)\s*$", re.MULTILINE)
_LINKED = re.compile(r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+#(\d+)")
_MARKER = re.compile(r"mark\.req\(([^)]*)\)")


def linked_issue(pr_body: str) -> int | None:
    m = _LINKED.search(pr_body or "")
    return int(m.group(1)) if m else None


def parse_criteria(text: str, source: str) -> list[AcceptanceCriterion]:
    return [AcceptanceCriterion(id=m.group(1).replace("-", "").upper(), text=m.group(2), source=source)
            for m in _AC_LINE.finditer(text or "")]


def collect(pr_body: str, issue_body: str | None, issue_number: int | None) -> list[AcceptanceCriterion]:
    """Issue criteria are the contract; the PR description can add more but cannot redefine them."""
    criteria: dict[str, AcceptanceCriterion] = {}
    for ac in parse_criteria(pr_body, "PR description"):
        criteria[ac.id] = ac
    for ac in parse_criteria(issue_body or "", f"issue #{issue_number}" if issue_number else "issue"):
        criteria[ac.id] = ac
    return sorted(criteria.values(), key=lambda a: int(re.sub(r"\D", "", a.id) or 0))


def declared_in_tests(root: Path) -> set[str]:
    """AC ids referenced by @pytest.mark.req anywhere in the repo's tests (read statically)."""
    ids: set[str] = set()
    for path in root.rglob("test*.py"):
        if any(part.startswith(".") or part in ("node_modules", "venv") for part in path.parts):
            continue
        for args in _MARKER.findall(path.read_text(errors="ignore")):
            ids.update(m.replace("-", "").upper() for m in re.findall(r"AC-?\d+", args))
    return ids


def trace(criteria: list[AcceptanceCriterion], tests: list[TestResult], declared: set[str]) -> list[ACTrace]:
    traces = []
    for ac in criteria:
        tagged = [t for t in tests if ac.id in {r.replace("-", "").upper() for r in t.requirement_ids}]
        covering = [t for t in tagged if t.message != "skipped"]
        passed = sum(t.passed for t in covering)
        status: ACStatus
        if not covering and tagged:
            status, evidence = "not_run", f"Its {len(tagged)} linked test(s) are skipped — nothing proves it."
        elif not covering and ac.id in declared:
            status, evidence = "not_run", "Tests are tagged with this criterion but did not run."
        elif not covering:
            status, evidence = "untested", "No test is tagged with this criterion — nothing proves it."
        elif passed == len(covering):
            status, evidence = "proven", f"{passed}/{len(covering)} linked tests pass."
        else:
            status, evidence = "failing", f"{len(covering) - passed}/{len(covering)} linked tests fail."
        traces.append(ACTrace(id=ac.id, text=ac.text, source=ac.source, status=status,
                              tests=[t.nodeid for t in tagged], evidence=evidence))
    return traces
