"""Data model shared by the engine, the API, the CLI and (as JSON) the web UI."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["critical", "high", "medium", "low", "info"]
StageId = Literal[
    "generate", "parse", "imports", "lint", "types", "complexity",
    "security", "tests", "coverage", "mutation", "requirements", "gate",
]
StageStatus = Literal["idle", "running", "pass", "warn", "fail", "skipped"]
RequirementStatus = Literal["met", "partial", "missing", "untested"]
IterationSource = Literal["input", "generated", "llm-repair", "replay-repair"]

STAGE_ORDER: list[StageId] = [
    "parse", "imports", "lint", "types", "complexity",
    "security", "tests", "coverage", "mutation", "requirements", "gate",
]


class Issue(BaseModel):
    stage: StageId
    rule: str
    severity: Severity
    message: str
    line: int | None = None


class Requirement(BaseModel):
    id: str
    text: str


class TestResult(BaseModel):
    __test__ = False  # not a pytest test class

    name: str
    requirement_ids: list[str] = Field(default_factory=list)
    passed: bool
    message: str | None = None
    duration_ms: float = 0.0


class RequirementTrace(BaseModel):
    id: str
    text: str
    status: RequirementStatus
    tests: list[str]
    evidence: str
    source: Literal["tests", "llm-judge", "tests+llm-judge"] = "tests"


class FunctionMetric(BaseModel):
    name: str
    line: int
    complexity: int
    rank: str
    length: int
    max_depth: int
    params: int


class Mutant(BaseModel):
    id: int
    line: int
    description: str
    killed: bool


class Coverage(BaseModel):
    line_percent: float
    branch_percent: float | None
    missing_lines: list[int]


class Scores(BaseModel):
    correctness: int
    requirements: int
    security: int
    test_strength: int
    maintainability: int
    style: int


class Gate(BaseModel):
    passed: bool
    overall: int
    threshold: int
    blockers: list[str]
    # Blockers the AI is allowed to fix by rewriting the code. Anything else
    # (weak tests, missing tests) is escalated to a human.
    repairable: bool
    escalations: list[str] = Field(default_factory=list)


class Report(BaseModel):
    iteration: int
    code: str
    issues: list[Issue]
    tests: list[TestResult]
    test_load_error: str | None = None
    coverage: Coverage | None
    mutants: list[Mutant]
    requirements: list[RequirementTrace]
    functions: list[FunctionMetric]
    maintainability_index: float | None
    scores: Scores
    gate: Gate
    lines_of_code: int


class RunRequest(BaseModel):
    spec: str
    code: str = ""
    tests: str
    sample_id: str | None = None
    generate: bool = False
    auto_repair: bool = True
    max_iterations: int = Field(default=3, ge=1, le=5)
    allowed_packages: list[str] = Field(default_factory=list)


class Sample(BaseModel):
    id: str
    title: str
    tagline: str
    spec: str
    tests: str
    # What the "AI" first produced — deliberately flawed so the gate has something to catch.
    generated: str
    # Recorded fix used in replay mode (no API key needed for the demo).
    repaired: str
