"""Runs the gate stage by stage and drives the generate → verify → repair loop.

`run()` is a generator of JSON-able events so the same code powers the live
dashboard (streamed over HTTP), the CLI and the GitHub Action.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from typing import Any

from sentinel import gate, llm
from sentinel.models import Issue, IterationSource, Report, RunRequest, StageId, StageStatus
from sentinel.samples import SAMPLES
from sentinel.stages import dynamic, requirements, static
from sentinel.workspace import Workspace

Event = dict[str, Any]


def _status(issues: list[Issue]) -> StageStatus:
    if any(i.severity in ("critical", "high") for i in issues):
        return "fail"
    return "warn" if issues else "pass"


def _summary(issues: list[Issue]) -> str:
    return "clean" if not issues else f"{len(issues)} finding{'s' if len(issues) != 1 else ''}"


class _Stages:
    """Times each stage and emits running/finished events. `pace` slows stages down for the UI animation only."""

    def __init__(self, iteration: int, pace: float) -> None:
        self.iteration, self.pace = iteration, pace
        self.result: Any = None

    def run(self, stage: StageId, fn: Callable[[], Any], verdict: Callable[[Any], tuple[StageStatus, str]]) -> Iterator[Event]:
        yield {"type": "stage", "iteration": self.iteration, "stage": stage, "status": "running"}
        start = time.perf_counter()
        result = fn()
        elapsed = time.perf_counter() - start
        if elapsed < self.pace:
            time.sleep(self.pace - elapsed)
        status, summary = verdict(result)
        self.result = result
        yield {"type": "stage", "iteration": self.iteration, "stage": stage, "status": status,
               "summary": summary, "duration_ms": round(elapsed * 1000)}

    def skip(self, stage: StageId, why: str) -> Event:
        return {"type": "stage", "iteration": self.iteration, "stage": stage, "status": "skipped", "summary": why}


def evaluate(code: str, req: RunRequest, iteration: int = 1, pace: float = 0.0,
             use_judge: bool = False) -> Iterator[Event]:
    """Runs every stage on one version of the code; the last event carries the Report."""
    s = _Stages(iteration, pace)
    issues: list[Issue] = []

    yield from s.run("parse", lambda: static.parse(code), lambda r: (_status(r), "valid Python" if not r else r[0].message))
    issues += s.result
    parsed = not s.result
    ws = Workspace(code, req.tests)
    try:
        if parsed:
            yield from s.run("imports", lambda: static.imports(code, req.allowed_packages), lambda r: (_status(r), _summary(r)))
            issues += s.result
            yield from s.run("lint", lambda: static.lint(ws), lambda r: (_status(r), _summary(r)))
            issues += s.result
            yield from s.run("types", lambda: static.types(ws), lambda r: (_status(r), _summary(r)))
            issues += s.result
            yield from s.run("complexity", lambda: static.complexity(code),
                             lambda r: (_status(r[0]), f"max CC {max((f.complexity for f in r[1]), default=0)} · MI {r[2]}"))
            cx_issues, functions, mi = s.result
            issues += cx_issues
            yield from s.run("security", lambda: static.security(ws), lambda r: (_status(r), _summary(r)))
            issues += s.result
        else:
            functions, mi = [], None
            skipped: list[StageId] = ["imports", "lint", "types", "complexity", "security"]
            for stage in skipped:
                yield s.skip(stage, "code does not parse")

        if parsed:
            yield from s.run("tests", lambda: dynamic.run_tests(ws), lambda r: (
                "fail" if r.load_error or any(not t.passed for t in r.results) else "pass",
                "suite crashed" if r.load_error else f"{sum(t.passed for t in r.results)}/{len(r.results)} passed"))
            test_run: dynamic.TestRun = s.result
        else:
            test_run = dynamic.TestRun([], None, "code does not parse")
            yield s.skip("tests", "code does not parse")

        cov = test_run.coverage
        if cov:
            yield {"type": "stage", "iteration": iteration, "stage": "coverage",
                   "status": "pass" if cov.line_percent >= gate.MIN_COVERAGE else "warn",
                   "summary": f"{cov.line_percent}% lines" + (f" · {cov.branch_percent}% branches" if cov.branch_percent is not None else "")}
        else:
            yield s.skip("coverage", "no coverage data")

        # Mutation testing only means something once the real code passes the tests.
        green = bool(test_run.results) and not test_run.load_error and all(t.passed for t in test_run.results)
        mutants = []
        if green:
            yield from s.run("mutation", lambda: dynamic.mutation(ws, code), lambda r: (
                "pass" if (gate.mutation_score(r) or 100) >= gate.MIN_MUTATION_SCORE else "warn",
                f"{sum(m.killed for m in r)}/{len(r)} mutants killed"))
            mutants = s.result
        else:
            yield s.skip("mutation", "runs once all tests pass")

        def trace() -> list[Any]:
            reqs = requirements.parse_requirements(req.spec)
            traces = requirements.trace(reqs, test_run.results, req.tests)
            if use_judge and reqs:
                traces = requirements.merge_judge(traces, llm.judge(req.spec, code, [r.id for r in reqs]))
            return traces

        yield from s.run("requirements", trace, lambda r: (
            "pass" if r and all(t.status == "met" for t in r) else ("fail" if any(t.status == "missing" for t in r) else "warn"),
            f"{sum(t.status == 'met' for t in r)}/{len(r)} proven"))
        traces = s.result

        scores = gate.score(issues, test_run.results, cov, mutants, traces)
        decision = gate.decide(scores, issues, test_run.results, test_run.load_error, cov, mutants, traces)
        yield {"type": "stage", "iteration": iteration, "stage": "gate", "status": "pass" if decision.passed else "fail",
               "summary": f"{decision.overall}/100 · {'PASS' if decision.passed else 'BLOCKED'}"}

        report = Report(
            iteration=iteration, code=code, issues=issues, tests=test_run.results, test_load_error=test_run.load_error,
            coverage=cov, mutants=mutants, requirements=traces, functions=functions, maintainability_index=mi,
            scores=scores, gate=decision, lines_of_code=len([ln for ln in code.splitlines() if ln.strip()]),
        )
        yield {"type": "report", "report": report.model_dump()}
    finally:
        ws.cleanup()


def run(req: RunRequest, pace: float = 0.0) -> Iterator[Event]:
    live = llm.is_live()
    sample = SAMPLES.get(req.sample_id or "")
    yield {"type": "mode", "mode": "live" if live else "replay", "model": llm.MODEL if live else None}

    code, source = req.code, "input"
    if req.generate:
        yield {"type": "stage", "iteration": 1, "stage": "generate", "status": "running"}
        if live:
            out = llm.generate(req.spec)
            code, source = out.code, "generated"
            yield {"type": "log", "level": "info", "message": f"Claude: {out.notes}"}
        elif sample:
            time.sleep(pace * 2)
            code, source = sample.generated, "generated"
            yield {"type": "log", "level": "info", "message": "Replay mode: using the recorded AI output for this sample."}
        else:
            yield {"type": "log", "level": "error", "message": "Generation needs ANTHROPIC_API_KEY (or pick a sample for replay mode)."}
            yield {"type": "done", "passed": False, "iterations": 0}
            return
        yield {"type": "stage", "iteration": 1, "stage": "generate", "status": "pass", "summary": f"{len(code.splitlines())} lines"}

    for iteration in range(1, req.max_iterations + 1):
        yield {"type": "iteration", "iteration": iteration, "source": source, "code": code}
        report: Report | None = None
        for event in evaluate(code, req, iteration, pace, use_judge=live):
            if event["type"] == "report":
                report = Report.model_validate(event["report"])
            yield event
        assert report is not None

        if report.gate.passed:
            yield {"type": "done", "passed": True, "iterations": iteration}
            return
        if not req.auto_repair or iteration == req.max_iterations:
            break
        if not report.gate.repairable:
            yield {"type": "log", "level": "warn",
                   "message": "Remaining blockers need a human (tests/spec), so the AI is not asked to retry."}
            break

        next_source: IterationSource
        if live:
            yield {"type": "log", "level": "info", "message": f"Sending {len(report.gate.blockers)} blocker(s) back to Claude…"}
            out = llm.repair(req.spec, code, report)
            code, next_source = out.code, "llm-repair"
            yield {"type": "log", "level": "info", "message": f"Claude: {out.notes}"}
        elif sample and code.strip() == sample.generated.strip():
            code, next_source = sample.repaired, "replay-repair"
            yield {"type": "log", "level": "info", "message": "Replay mode: applying the recorded AI repair."}
        else:
            yield {"type": "log", "level": "warn", "message": "No recorded repair for this code. Set ANTHROPIC_API_KEY for live repair."}
            break
        source = next_source

    yield {"type": "done", "passed": False, "iterations": iteration}
