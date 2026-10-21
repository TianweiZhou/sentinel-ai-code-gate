// Mirrors sentinel/models.py (the API sends these as JSON).

export type Severity = "critical" | "high" | "medium" | "low" | "info";
export type StageId =
  | "generate" | "parse" | "imports" | "lint" | "types" | "complexity"
  | "security" | "tests" | "coverage" | "mutation" | "requirements" | "gate";
export type StageStatus = "idle" | "running" | "pass" | "warn" | "fail" | "skipped";
export type IterationSource = "input" | "generated" | "llm-repair" | "replay-repair";

export interface Issue { stage: StageId; rule: string; severity: Severity; message: string; line: number | null }
export interface TestResult { name: string; requirement_ids: string[]; passed: boolean; message: string | null; duration_ms: number }
export interface RequirementTrace {
  id: string; text: string; status: "met" | "partial" | "missing" | "untested";
  tests: string[]; evidence: string; source: string;
}
export interface FunctionMetric { name: string; line: number; complexity: number; rank: string; length: number; max_depth: number; params: number }
export interface Mutant { id: number; line: number; description: string; killed: boolean }
export interface Coverage { line_percent: number; branch_percent: number | null; missing_lines: number[] }
export interface Scores { correctness: number; requirements: number; security: number; test_strength: number; maintainability: number; style: number }
export interface Gate { passed: boolean; overall: number; threshold: number; blockers: string[]; repairable: boolean; escalations: string[] }

export interface Report {
  iteration: number; code: string; issues: Issue[]; tests: TestResult[]; test_load_error: string | null;
  coverage: Coverage | null; mutants: Mutant[]; requirements: RequirementTrace[]; functions: FunctionMetric[];
  maintainability_index: number | null; scores: Scores; gate: Gate; lines_of_code: number;
}

export interface Sample { id: string; title: string; tagline: string; spec: string; tests: string; generated: string; repaired: string }

export type PipelineEvent =
  | { type: "mode"; mode: "live" | "replay"; model: string | null }
  | { type: "iteration"; iteration: number; source: IterationSource; code: string }
  | { type: "stage"; iteration: number; stage: StageId; status: StageStatus; summary?: string; duration_ms?: number }
  | { type: "report"; report: Report }
  | { type: "log"; level: "info" | "warn" | "error"; message: string }
  | { type: "done"; passed: boolean; iterations: number };

export interface Health {
  mode: "live" | "replay"; model: string | null; weights: Record<keyof Scores, number>;
  threshold: number; min_coverage: number; min_mutation_score: number;
}

export const STAGES: { id: StageId; label: string; hint: string }[] = [
  { id: "generate", label: "Generate", hint: "LLM writes code from the spec only — tests stay hidden" },
  { id: "parse", label: "Parse", hint: "Is it valid Python?" },
  { id: "imports", label: "Imports", hint: "Hallucinated packages & APIs, dependency allow-list" },
  { id: "lint", label: "Lint", hint: "ruff — bugs, idioms, naming" },
  { id: "types", label: "Types", hint: "mypy --strict" },
  { id: "complexity", label: "Complexity", hint: "radon — cyclomatic, nesting, length" },
  { id: "security", label: "Security", hint: "bandit — injection, eval, weak crypto, secrets" },
  { id: "tests", label: "Tests", hint: "pytest acceptance tests in an isolated process" },
  { id: "coverage", label: "Coverage", hint: "line & branch coverage" },
  { id: "mutation", label: "Mutation", hint: "plant bugs — do the tests notice?" },
  { id: "requirements", label: "Trace", hint: "every requirement proven by a passing test" },
  { id: "gate", label: "Gate", hint: "weighted score + hard rules" },
];
