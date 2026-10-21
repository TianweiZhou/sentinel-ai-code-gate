"""Renders a Report for people: the PR summary comment, inline line comments and a terminal view."""

from __future__ import annotations

from sentinel.models import Finding, Report
from sentinel.verdict import failing_tests, mutation_score

SUMMARY_MARKER = "<!-- sentinel:summary -->"
INLINE_MARKER = "<!-- sentinel:inline -->"
ICON = {"ready": "✅", "after_checks": "🟡", "do_not_merge": "⛔"}
_AC_ICON = {"proven": "✅", "failing": "⛔", "not_run": "⛔", "untested": "🟡", "disputed": "🟡"}
_SEV_ICON = {"critical": "⛔", "high": "⛔", "medium": "🟡", "low": "·", "info": "·"}


def _where(f: Finding) -> str:
    return f"`{f.path}:{f.line}`" if f.line else f"`{f.path}`"


def stats_line(r: Report) -> str:
    proven = sum(c.status == "proven" for c in r.criteria)
    ran = [t for t in r.tests if t.message != "skipped"]
    parts = [
        f"**{r.overall}/100**",
        f"{len(r.changed_files)} files, +{sum(len(f.added_lines) for f in r.changed_files)} lines",
        f"criteria {proven}/{len(r.criteria)} proven" if r.criteria else "no criteria",
        f"tests {len(ran) - len(failing_tests(r.tests))}/{len(ran)} passing" if ran else "no tests ran",
    ]
    if r.coverage and r.coverage.percent is not None:
        parts.append(f"changed-line coverage {r.coverage.percent:.0f}%")
    if (ms := mutation_score(r.mutants)) is not None:
        parts.append(f"planted bugs caught {ms:.0f}%")
    return " · ".join(parts)


def markdown(r: Report) -> str:
    v = r.verdict
    lines = [SUMMARY_MARKER, f"## {ICON[v.kind]} Sentinel: {v.headline}", "", stats_line(r), ""]
    if v.blockers:
        lines += ["### Why not", *[f"- ⛔ {b}" for b in v.blockers], ""]
    if v.checks:
        lines += ["### Needs a human look", *[f"- 🟡 {c}" for c in v.checks], ""]
    if r.criteria:
        src = r.criteria[0].source
        lines += [f"### Acceptance criteria ({src})", "", "| | | Criterion | Evidence |", "|---|---|---|---|"]
        lines += [f"| {_AC_ICON[c.status]} | **{c.id}** | {c.text} | {c.evidence} |" for c in r.criteria]
        lines.append("")
    lines += ["### Reviewer checklist", *[f"- [ ] {h}" for h in v.human_review], ""]
    shown = [f for f in r.findings if f.severity in ("critical", "high", "medium")]
    if shown:
        lines += ["<details><summary>Findings on changed lines (" + str(len(shown)) + ")</summary>", "",
                  "| | Check | Where | Detail |", "|---|---|---|---|"]
        lines += [f"| {_SEV_ICON[f.severity]} | {f.stage}/{f.rule}{' (AI)' if f.source == 'ai' else ''} | {_where(f)} | "
                  f"{f.message.replace('|', '/')} |" for f in shown[:40]]
        lines += ["", "</details>", ""]
    if r.ai_summary:
        lines += [f"> **AI reviewer:** {r.ai_summary}", ""]
    survived = [m for m in r.mutants if not m.killed]
    if survived:
        lines += ["<details><summary>Planted bugs the tests did not catch</summary>", ""]
        lines += [f"- `{m.path}:{m.line}` {m.description}" for m in survived]
        lines += ["", "</details>", ""]
    lines.append("<sub>Sentinel advises; it never merges. Tools and tests decide ⛔ and ✅, the AI reviewer can only "
                 "escalate to 🟡, and the reviewer owns the merge.</sub>")
    return "\n".join(lines)


def inline_comments(r: Report, limit: int = 25) -> list[dict[str, object]]:
    """Review comments for findings on lines this PR added (GitHub only accepts lines in the diff)."""
    added = {(f.path, ln) for f in r.changed_files for ln in f.added_lines}
    comments: list[dict[str, object]] = []
    for f in r.findings:
        if f.severity not in ("critical", "high", "medium") or (f.path, f.line) not in added:
            continue
        who = "AI reviewer" if f.source == "ai" else f"{f.stage} · {f.rule}"
        comments.append({"path": f.path, "line": f.line, "side": "RIGHT",
                         "body": f"{INLINE_MARKER}\n{_SEV_ICON[f.severity]} **{who}**: {f.message}"})
    return comments[:limit]


def terminal(r: Report) -> str:
    v = r.verdict
    color = {"ready": "\033[32m", "after_checks": "\033[33m", "do_not_merge": "\033[31m"}[v.kind]
    out = [f"\n{color}\033[1m{ICON[v.kind]} {v.headline}\033[0m  {stats_line(r).replace('**', '')}"]
    out += [f"  \033[31m⛔ {b}\033[0m" for b in v.blockers]
    out += [f"  \033[33m🟡 {c}\033[0m" for c in v.checks]
    out.append("  Reviewer checklist:")
    out += [f"   [ ] {h}" for h in v.human_review]
    return "\n".join(out)
