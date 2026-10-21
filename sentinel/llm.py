"""Claude integration: write code, repair code, and review requirements.

Design rules that matter for quality:
  * The model sees the spec, never the test source. Tests are a held-out exam;
    showing them invites code that special-cases the asserts.
  * On repair it gets the *failures* (test names, assertion messages, findings),
    not the tests themselves.
  * Every response is structured JSON validated by Pydantic — no regex-parsing
    of markdown code fences.
"""

from __future__ import annotations

import os
from typing import Literal

import anthropic
from pydantic import BaseModel

from sentinel.models import Report

MODEL = os.environ.get("SENTINEL_MODEL", "claude-opus-5-5")
# Server-side fallbacks: if a request is declined by a safety classifier the API
# re-runs it on a suitable model inside the same call.
_BETAS = ["server-side-fallback-2026-07-01"]

SYSTEM = """You are a senior Python engineer writing production code that will be checked by an automated quality gate:
ruff, mypy --strict, bandit, radon complexity limits (cyclomatic <= 8, nesting <= 3, <= 40 lines per function),
hidden pytest acceptance tests, coverage and mutation testing.
Write a single self-contained module named solution.py. Use only the Python standard library.
Fully type-annotate everything. Prefer small functions. Never use eval/exec, string-built SQL, shell=True,
md5/sha1 for security, or the `random` module for secrets. Raise ValueError for invalid input unless the spec says otherwise."""


class CodeOut(BaseModel):
    code: str
    notes: str


class Verdict(BaseModel):
    id: str
    status: str  # met | partial | missing
    evidence: str


class JudgeOut(BaseModel):
    verdicts: list[Verdict]


def is_live() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                or os.environ.get("SENTINEL_LIVE"))


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


Effort = Literal["low", "medium", "high", "xhigh", "max"]


def _parse[T: BaseModel](schema: type[T], prompt: str, effort: Effort) -> T:
    response = _client().beta.messages.parse(
        model=MODEL,
        max_tokens=16000,
        betas=_BETAS,
        fallbacks="default",
        system=SYSTEM,
        output_config={"effort": effort},
        output_format=schema,
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("The model declined this request.")
    if response.parsed_output is None:
        raise RuntimeError(f"Model output did not match the schema (stop_reason={response.stop_reason}).")
    return response.parsed_output


def generate(spec: str) -> CodeOut:
    return _parse(CodeOut, f"Implement this specification.\n\n<spec>\n{spec}\n</spec>\n\n"
                           "Return the full contents of solution.py in `code` and a one-line summary in `notes`.", "high")


def _feedback(report: Report) -> str:
    lines = [f"- BLOCKER: {b}" for b in report.gate.blockers if b not in report.gate.escalations]
    for t in report.tests:
        if not t.passed:
            lines.append(f"- Failing test `{t.name}` (verifies {', '.join(t.requirement_ids) or 'n/a'}): {t.message}")
    if report.test_load_error:
        lines.append(f"- Test suite crashed while importing your module: {report.test_load_error[-600:]}")
    for i in report.issues:
        if i.severity in ("critical", "high", "medium"):
            lines.append(f"- [{i.stage}/{i.rule}] line {i.line}: {i.message}")
    return "\n".join(lines[:60])


def repair(spec: str, code: str, report: Report) -> CodeOut:
    prompt = (
        f"Your previous solution.py was blocked by the quality gate (score {report.gate.overall}/100).\n\n"
        f"<spec>\n{spec}\n</spec>\n\n<previous_code>\n{code}\n</previous_code>\n\n"
        f"<gate_feedback>\n{_feedback(report)}\n</gate_feedback>\n\n"
        "Fix the root causes, not the symptoms: do not special-case test inputs or silence the tools "
        "(no `# type: ignore`, `# noqa`, `# nosec`). Return the complete new solution.py in `code` and say "
        "what you changed in `notes`."
    )
    return _parse(CodeOut, prompt, "high")


def judge(spec: str, code: str, requirement_ids: list[str]) -> dict[str, tuple[str, str]]:
    prompt = (
        "Act as a strict code reviewer. For each requirement id below decide whether the code satisfies it: "
        "`met`, `partial` or `missing`. Quote the line(s) that justify it in `evidence` (max 25 words).\n\n"
        f"Requirement ids: {', '.join(requirement_ids)}\n\n<spec>\n{spec}\n</spec>\n\n<code>\n{code}\n</code>"
    )
    out = _parse(JudgeOut, prompt, "medium")
    return {v.id: (v.status if v.status in ("met", "partial", "missing") else "partial", v.evidence) for v in out.verdicts}
