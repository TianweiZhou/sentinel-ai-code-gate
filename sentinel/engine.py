"""Runs every stage on a pull request and yields progress events, ending with the Report.

The same generator drives the CLI, the GitHub Action and the review console (streamed over HTTP).
"""

from __future__ import annotations

import datetime as dt
import shutil
import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from sentinel import ai_review, config, repo, verdict
from sentinel.models import (
    ACTrace,
    ChangedFile,
    DiffCoverage,
    Finding,
    FunctionMetric,
    Mutant,
    PullRequestInfo,
    Report,
    StageId,
    StageResult,
    StageStatus,
)
from sentinel.stages import dynamic, integrity, requirements, static

Event = dict[str, Any]


def _status(findings: list[Finding]) -> StageStatus:
    if any(f.severity in ("critical", "high") for f in findings):
        return "fail"
    return "warn" if any(f.severity == "medium" for f in findings) else "pass"


def _count(findings: list[Finding]) -> str:
    return "clean" if not findings else f"{len(findings)} found"


class _Runner:
    """Times stages, records their results and emits events. `pace` only slows things down for the UI animation."""

    def __init__(self, pace: float) -> None:
        self.pace = pace
        self.stages: dict[str, StageResult] = {}
        self.result: Any = None

    def run(self, stage: StageId, fn: Callable[[], Any], judge: Callable[[Any], tuple[StageStatus, str]]) -> Iterator[Event]:
        yield {"type": "stage", "stage": stage, "status": "running"}
        start = time.perf_counter()
        self.result = fn()
        elapsed = time.perf_counter() - start
        if elapsed < self.pace:
            time.sleep(self.pace - elapsed)
        status, summary = judge(self.result)
        yield from self.set(stage, status, summary, round(elapsed * 1000))

    def set(self, stage: StageId, status: StageStatus, summary: str, ms: int = 0) -> Iterator[Event]:
        self.stages[stage] = StageResult(status=status, summary=summary, duration_ms=ms)
        yield {"type": "stage", "stage": stage, "status": status, "summary": summary, "duration_ms": ms}


def review(root: Path, base: str, head: str = "HEAD", pr: PullRequestInfo | None = None, pr_body: str = "",
           issue_body: str | None = None, use_ai: bool | None = None, pace: float = 0.0) -> Iterator[Event]:
    root = root.resolve()
    cfg = config.load(root)
    pr = pr or PullRequestInfo(base=base, head=head)
    r = _Runner(pace)
    findings: list[Finding] = []

    yield from r.run("diff", lambda: repo.changed_files(root, base, head),
                     lambda fs: ("pass", f"{len(fs)} files, +{sum(len(f.added_lines) for f in fs)}"))
    files: list[ChangedFile] = r.result

    criteria = requirements.collect(pr_body, issue_body, pr.linked_issue)
    yield from r.set("requirements", "pass" if criteria else "warn",
                     f"{len(criteria)} criteria" if criteria else "none found")

    first_party = repo.first_party_packages(root)
    for stage, fn in (("imports", lambda: static.imports(root, files, cfg, first_party)),
                      ("lint", lambda: static.lint(root, files, cfg)),
                      ("types", lambda: static.types(root, files, cfg))):
        yield from r.run(stage, fn, lambda fs: (_status(fs), _count(fs)))  # type: ignore[arg-type]
        findings += r.result

    yield from r.run("complexity", lambda: static.complexity(root, files, cfg),
                     lambda res: (_status(res[0]),
                                  f"max {max((m.complexity for m in res[1]), default=0)}"))
    cx_findings, functions = r.result
    findings += cx_findings
    functions_: list[FunctionMetric] = functions

    yield from r.run("security", lambda: static.security(root, files), lambda fs: (_status(fs), _count(fs)))
    findings += r.result
    yield from r.run("integrity", lambda: integrity.check(root, base, files, cfg), lambda fs: (_status(fs), _count(fs)))
    findings += r.result

    sandbox = dynamic.sandbox_copy(root)
    try:
        yield from r.run("tests", lambda: dynamic.run_tests(sandbox, files), lambda t: (
            "fail" if t.error or verdict.failing_tests(t.results) else "pass",
            "crashed" if t.error else f"{sum(x.passed for x in t.results)}/{len(t.results)}"))
        test_run: dynamic.TestRun = r.result
        cov: DiffCoverage | None = test_run.coverage
        yield from r.set("coverage", "skipped" if cov is None or cov.percent is None else
                         ("pass" if cov.percent >= cfg.min_diff_coverage else "warn"),
                         "n/a" if cov is None or cov.percent is None else f"{cov.percent:.0f}%")

        mutants: list[Mutant] = []
        green = test_run.results and not test_run.error and not verdict.failing_tests(test_run.results)
        if green and static.python_sources(files, include_tests=False):
            yield from r.run("mutation", lambda: dynamic.mutation(sandbox, files, cfg), lambda ms: (
                "skipped" if not ms else ("pass" if (verdict.mutation_score(ms) or 0) >= cfg.min_mutation_score else "warn"),
                f"{sum(m.killed for m in ms)}/{len(ms)} caught" if ms else "n/a"))
            mutants = r.result
        else:
            yield from r.set("mutation", "skipped", "after tests pass")
    finally:
        shutil.rmtree(sandbox.parent, ignore_errors=True)

    traces: list[ACTrace] = requirements.trace(criteria, test_run.results, requirements.declared_in_tests(root))
    ai_focus: list[str] = []
    ai_summary = None
    ai_on = ai_review.enabled() if use_ai is None else use_ai
    if ai_on:
        yield from r.run("ai_review", lambda: ai_review.review(root, files, traces, test_run.results, pr.title, pr_body,
                                                               issue_body),
                         lambda out: ("warn" if out.comments else "pass", f"{len(out.comments)} notes"))
        out: ai_review.ReviewOut = r.result
        traces = ai_review.apply_to_criteria(traces, out)
        findings += ai_review.to_findings(out, files)
        ai_focus, ai_summary = out.human_focus, out.summary
    else:
        yield from r.set("ai_review", "skipped", "off")

    scores, overall = verdict.score(traces, findings, test_run.results, test_run.error, cov, mutants)
    decision = verdict.decide(traces, findings, test_run.results, test_run.error, cov, mutants, functions_, cfg, ai_focus)
    stage_status: dict[str, StageStatus] = {"ready": "pass", "after_checks": "warn", "do_not_merge": "fail"}
    short = {"ready": "ready", "after_checks": "check first", "do_not_merge": "blocked"}[decision.kind]
    yield from r.set("verdict", stage_status[decision.kind], short)

    report = Report(
        id=f"{(pr.repo or root.name).replace('/', '__')}__{pr.number or 'local'}__{uuid.uuid4().hex[:6]}",
        created_at=dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), pr=pr, changed_files=files,
        criteria=traces, findings=findings, tests=test_run.results, test_error=test_run.error, coverage=cov,
        mutants=mutants, functions=functions_, ai_summary=ai_summary, ai_enabled=ai_on, stages=r.stages,
        scores=scores, overall=overall, verdict=decision,
    )
    yield {"type": "report", "report": report.model_dump()}
