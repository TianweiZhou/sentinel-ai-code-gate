"""Command line entry point — the same gate the dashboard runs, for terminals and CI.

    sentinel check solution.py --tests test_solution.py --spec SPEC.md
    sentinel check --sample signup --repair
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sentinel import pipeline
from sentinel.models import Report, RunRequest
from sentinel.samples import SAMPLES

_ICON = {"pass": "✔", "warn": "▲", "fail": "✖", "skipped": "·"}
_COLOR = {"pass": "\033[32m", "warn": "\033[33m", "fail": "\033[31m", "skipped": "\033[90m"}
_RESET = "\033[0m"


def _markdown(report: Report) -> str:
    """Summary posted as a pull-request comment by the GitHub Action."""
    g = report.gate
    head = f"## {'✅ Sentinel: PASS' if g.passed else '⛔ Sentinel: BLOCKED'} — {g.overall}/100 (threshold {g.threshold})"
    rows = "\n".join(f"| {k.replace('_', ' ')} | {v} |" for k, v in report.scores.model_dump().items())
    reqs = "\n".join(f"| {r.id} | {r.status} | {r.evidence} |" for r in report.requirements)
    blockers = "\n".join(f"- {b}" for b in g.blockers) or "- none"
    issues = "\n".join(
        f"- `{i.severity}` **{i.stage}/{i.rule}** line {i.line}: {i.message}"
        for i in report.issues if i.severity in ("critical", "high", "medium")
    ) or "- none"
    killed = sum(m.killed for m in report.mutants)
    cov = f"{report.coverage.line_percent}%" if report.coverage else "n/a"
    return (f"{head}\n\n### Blockers\n{blockers}\n\n| dimension | score |\n|---|---|\n{rows}\n\n"
            f"**Coverage** {cov} · **Mutants killed** {killed}/{len(report.mutants)}\n\n"
            f"### Requirements\n| id | status | evidence |\n|---|---|---|\n{reqs}\n\n### Findings\n{issues}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sentinel", description="Quality gate for AI-generated Python code.")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="run the gate")
    check.add_argument("code", nargs="?", type=Path, help="module under test (imported by tests as `solution`)")
    check.add_argument("--tests", type=Path, help="pytest file; mark tests with @pytest.mark.req('R1')")
    check.add_argument("--spec", type=Path, help="spec with numbered requirements R1:, R2:, …")
    check.add_argument("--sample", choices=sorted(SAMPLES), help="run a built-in demo scenario")
    check.add_argument("--repair", action="store_true", help="send blockers back to the LLM and retry")
    check.add_argument("--allow", action="append", default=[], help="approved third-party package (repeatable)")
    check.add_argument("--json", type=Path, help="write the final report as JSON")
    check.add_argument("--markdown", type=Path, help="write a Markdown summary (for PR comments)")
    args = parser.parse_args(argv)

    if args.sample:
        s = SAMPLES[args.sample]
        req = RunRequest(spec=s.spec, tests=s.tests, code=s.generated, sample_id=s.id, auto_repair=args.repair)
    elif args.code and args.tests and args.spec:
        req = RunRequest(spec=args.spec.read_text(), tests=args.tests.read_text(), code=args.code.read_text(),
                         auto_repair=args.repair, allowed_packages=args.allow)
    else:
        parser.error("give CODE --tests --spec, or --sample")

    report: Report | None = None
    for event in pipeline.run(req):
        kind = event["type"]
        if kind == "iteration":
            print(f"\n\033[1mIteration {event['iteration']}\033[0m ({event['source']})")
        elif kind == "stage" and event["status"] != "running":
            st = event["status"]
            print(f"  {_COLOR[st]}{_ICON[st]} {event['stage']:<13}{_RESET} {event.get('summary', '')}")
        elif kind == "log":
            print(f"  → {event['message']}")
        elif kind == "report":
            report = Report.model_validate(event["report"])
            for b in report.gate.blockers:
                print(f"    \033[31m⛔ {b}{_RESET}")

    if report is None:
        return 2
    print(f"\n{'PASS' if report.gate.passed else 'BLOCKED'} — {report.gate.overall}/100")
    if args.json:
        args.json.write_text(json.dumps(report.model_dump(), indent=2))
    if args.markdown:
        args.markdown.write_text(_markdown(report))
    return 0 if report.gate.passed else 1


if __name__ == "__main__":
    sys.exit(main())
