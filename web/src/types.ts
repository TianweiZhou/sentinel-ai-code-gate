// Mirrors sentinel/models.py (the API sends these as JSON).

export type Severity = "critical" | "high" | "medium" | "low" | "info";
export type StageId =
  | "diff" | "requirements" | "imports" | "lint" | "types" | "complexity" | "security"
  | "integrity" | "tests" | "coverage" | "mutation" | "ai_review" | "verdict";
export type StageStatus = "idle" | "running" | "pass" | "warn" | "fail" | "skipped";
export type VerdictKind = "ready" | "after_checks" | "do_not_merge";
export type ACStatus = "proven" | "failing" | "untested" | "not_run" | "disputed";

export interface Finding {
  stage: StageId; rule: string; severity: Severity; message: string;
  path: string | null; line: number | null; source: "tool" | "ai";
}
export interface ChangedFile { path: string; status: string; added_lines: number[]; is_test: boolean; patch: string }
export interface ACTrace { id: string; text: string; source: string; status: ACStatus; tests: string[]; evidence: string }
export interface TestResult { nodeid: string; requirement_ids: string[]; passed: boolean; message: string | null; duration_ms: number }
export interface Mutant { id: number; path: string; line: number; description: string; killed: boolean }
export interface DiffCoverage { covered: number; total: number; percent: number | null; uncovered: Record<string, number[]> }
export interface FunctionMetric { path: string; name: string; line: number; complexity: number; length: number; max_depth: number }
export interface Scores { requirements: number; correctness: number; security: number; test_strength: number; maintainability: number; integrity: number }
export interface Verdict { kind: VerdictKind; headline: string; blockers: string[]; checks: string[]; human_review: string[] }
export interface PullRequestInfo {
  repo: string | null; number: number | null; title: string; author: string | null; url: string | null;
  base: string; head: string; linked_issue: number | null;
}
export interface StageResult { status: StageStatus; summary: string; duration_ms: number }

export interface Report {
  id: string; created_at: string; pr: PullRequestInfo; changed_files: ChangedFile[]; criteria: ACTrace[];
  findings: Finding[]; tests: TestResult[]; test_error: string | null; coverage: DiffCoverage | null;
  mutants: Mutant[]; functions: FunctionMetric[]; ai_summary: string | null; ai_enabled: boolean;
  stages: Record<string, StageResult>; scores: Scores; overall: number; verdict: Verdict;
}

export interface ReportSummary {
  id: string; repo: string | null; number: number | null; title: string; author: string | null; url: string | null;
  verdict: VerdictKind; overall: number; created_at: string; blockers: number; checks: number;
}

export interface Health { ai_reviewer: boolean; model: string | null; reports_dir: string }

export type StreamEvent =
  | { type: "pr"; index: number; total: number; title: string; branch: string }
  | { type: "stage"; stage: StageId; status: StageStatus; summary?: string; duration_ms?: number }
  | { type: "report"; report: Report; summary: ReportSummary }
  | { type: "error"; message: string }
  | { type: "done" };

export const STAGES: { id: StageId; label: string; hint: string }[] = [
  { id: "diff", label: "Diff", hint: "What the PR changed — only added lines are judged" },
  { id: "requirements", label: "Criteria", hint: "Acceptance criteria from the linked issue" },
  { id: "imports", label: "Imports", hint: "Hallucinated packages/APIs, undeclared dependencies" },
  { id: "lint", label: "Lint", hint: "ruff with the repo's own config" },
  { id: "types", label: "Types", hint: "mypy with the repo's own config" },
  { id: "complexity", label: "Complexity", hint: "Functions the PR touched" },
  { id: "security", label: "Security", hint: "bandit on changed lines" },
  { id: "integrity", label: "Integrity", hint: "Deleted, skipped or weakened tests; secrets; silenced checks" },
  { id: "tests", label: "Tests", hint: "The repo's own test suite, in a sandbox copy" },
  { id: "coverage", label: "Coverage", hint: "Coverage of changed lines" },
  { id: "mutation", label: "Mutation", hint: "Plant bugs on changed lines — do the tests notice?" },
  { id: "ai_review", label: "AI review", hint: "Optional: intent vs. criteria and CLAUDE.md conventions (can only escalate)" },
  { id: "verdict", label: "Verdict", hint: "Ready / Merge after checks / Do not merge" },
];

export const VERDICT_META: Record<VerdictKind, { label: string; short: string; cls: string }> = {
  ready: { label: "Ready to merge", short: "Ready", cls: "ready" },
  after_checks: { label: "Merge after checks", short: "Needs a look", cls: "checks" },
  do_not_merge: { label: "Do not merge", short: "Blocked", cls: "block" },
};
