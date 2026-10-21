"""Data model shared by the engine, the CLI, the GitHub integration and (as JSON) the review console."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["critical", "high", "medium", "low", "info"]
StageId = Literal[
    "diff", "requirements", "imports", "lint", "types", "complexity", "security",
    "integrity", "tests", "coverage", "mutation", "ai_review", "verdict",
]
StageStatus = Literal["idle", "running", "pass", "warn", "fail", "skipped"]
VerdictKind = Literal["ready", "after_checks", "do_not_merge"]
ACStatus = Literal["proven", "failing", "untested", "not_run", "disputed"]

STAGE_ORDER: list[StageId] = [
    "diff", "requirements", "imports", "lint", "types", "complexity", "security",
    "integrity", "tests", "coverage", "mutation", "ai_review", "verdict",
]


class Finding(BaseModel):
    stage: StageId
    rule: str
    severity: Severity
    message: str
    path: str | None = None
    line: int | None = None
    source: Literal["tool", "ai"] = "tool"


class ChangedFile(BaseModel):
    path: str
    status: Literal["added", "modified", "deleted", "renamed"]
    added_lines: list[int] = Field(default_factory=list)
    is_test: bool = False
    patch: str = ""  # unified diff for this file (truncated), rendered by the console


class AcceptanceCriterion(BaseModel):
    id: str
    text: str
    source: str  # e.g. "issue #12" or "PR description"


class TestResult(BaseModel):
    __test__ = False  # not a pytest test class

    nodeid: str
    requirement_ids: list[str] = Field(default_factory=list)
    passed: bool
    message: str | None = None
    duration_ms: float = 0.0


class ACTrace(BaseModel):
    id: str
    text: str
    source: str
    status: ACStatus
    tests: list[str]
    evidence: str


class FunctionMetric(BaseModel):
    path: str
    name: str
    line: int
    complexity: int
    length: int
    max_depth: int


class Mutant(BaseModel):
    id: int
    path: str
    line: int
    description: str
    killed: bool


class DiffCoverage(BaseModel):
    covered: int
    total: int
    percent: float | None
    uncovered: dict[str, list[int]] = Field(default_factory=dict)


class Scores(BaseModel):
    requirements: int
    correctness: int
    security: int
    test_strength: int
    maintainability: int
    integrity: int


class Verdict(BaseModel):
    kind: VerdictKind
    headline: str
    blockers: list[str]          # reasons for ⛔
    checks: list[str]            # reasons for 🟡
    human_review: list[str]      # what a person still has to look at, whatever the verdict


class PullRequestInfo(BaseModel):
    repo: str | None = None
    number: int | None = None
    title: str = "Local review"
    author: str | None = None
    url: str | None = None
    base: str
    head: str
    linked_issue: int | None = None


class StageResult(BaseModel):
    status: StageStatus
    summary: str = ""
    duration_ms: int = 0


class Report(BaseModel):
    id: str
    created_at: str
    pr: PullRequestInfo
    changed_files: list[ChangedFile]
    criteria: list[ACTrace]
    findings: list[Finding]
    tests: list[TestResult]
    test_error: str | None = None
    coverage: DiffCoverage | None
    mutants: list[Mutant]
    functions: list[FunctionMetric]
    ai_summary: str | None = None
    ai_enabled: bool = False
    stages: dict[str, StageResult]
    scores: Scores
    overall: int
    verdict: Verdict
