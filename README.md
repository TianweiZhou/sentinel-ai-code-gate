# Sentinel: merge-readiness review for agent-written pull requests

[![CI](https://github.com/TianweiZhou/sentinel-ai-code-gate/actions/workflows/ci.yml/badge.svg)](https://github.com/TianweiZhou/sentinel-ai-code-gate/actions/workflows/ci.yml)
![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB)
![mypy strict](https://img.shields.io/badge/mypy-strict-2A6DB2)

Coding agents such as Claude Code and Codex now write many first drafts. The bottleneck has moved from writing code to
**deciding whether a pull request is safe to merge**.

Sentinel runs on every PR and gives the reviewer one of three answers, with the evidence behind it:

| | Verdict | Meaning |
|---|---|---|
| ✅ | **Ready to merge** | Every acceptance criterion is proven by a passing test, the tests are intact and strong, and nothing on the changed lines was flagged |
| 🟡 | **Merge after checks** | Nothing is proven wrong, but something needs a human look. Sentinel says exactly what |
| ⛔ | **Do not merge** | Hard evidence: a failing test or criterion, a security issue, an invented import, or tests that were deleted, skipped or weakened |

It **doesn't fix code and never merges**. Every verdict comes with a reviewer checklist of what tools can't decide.

> **AI advises, rules enforce, humans decide.** Tools and tests decide ⛔ and ✅. The optional AI reviewer can only
> escalate a PR to 🟡; it can never approve or block on its own.

Demo: [sentinel-demo-service](https://github.com/TianweiZhou/sentinel-demo-service/pulls) has three agent-written
PRs, one for each verdict.

---

## The three questions it answers

**1. Does the PR do what was asked?**
Acceptance criteria (`AC1: …`) come from the issue the PR closes. Each must be proven by a passing test tagged
`@pytest.mark.req("AC1")`. A criterion with no test is 🟡. A failing or skipped one is ⛔.

**2. Is it good code by this team's standards?**
ruff, mypy and bandit run with **the repo's own config**, plus complexity limits and import checks (invented packages
and APIs, undeclared new dependencies). Only findings on lines **the PR added** count, so legacy warnings don't drown
out the change. Optionally, Claude reviews the diff against each criterion and the repo's `CLAUDE.md` / `AGENTS.md`.

**3. Can we trust the tests that say so?**
- **Integrity:** existing tests deleted, newly skipped, or with fewer assertions than before are ⛔. These are the
  usual ways an agent turns CI green without fixing the problem. So are secrets in the diff. Silencing comments
  (`# noqa`, `# type: ignore`) and changes to CI or test config are 🟡.
- **Strength:** coverage of the **changed lines**, and **mutation testing on the changed lines**: Sentinel plants small
  bugs (`<` to `<=`, `+` to `-`, `return x` to `return None`) and checks that the tests notice.

## Where reviewers see it

- **On the PR:** one summary comment (verdict, reasons, acceptance-criteria table, reviewer checklist), inline comments
  on the exact lines, a `sentinel: ready / needs-human / do-not-merge` label, and a check that fails on ⛔.
- **Review console:** a local web app listing every reviewed PR across repos, worst first. Click one for the evidence:
  the pipeline, criteria, test strength, and the changed lines with findings, uncovered lines and uncaught bugs marked
  where they occur. It can sync verdicts from GitHub (`gh` CLI) or run the demo PRs live.

---

## Add it to any Python repository

```yaml
# .github/workflows/sentinel.yml
name: Sentinel review
on:
  pull_request:
    types: [opened, synchronize, reopened, edited]
permissions: { contents: read, pull-requests: write, issues: write }
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: TianweiZhou/sentinel-ai-code-gate@v2
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}   # optional: enables the AI reviewer
```

Tune it per repo in `pyproject.toml`. Everything has a default:

```toml
[tool.sentinel]
min_diff_coverage = 80
min_mutation_score = 70
max_complexity = 8
allowed_packages = []                 # approved even if not in [project] dependencies
sensitive_paths = ["migrations/"]     # any change here always needs a human
```

Then write issues with acceptance criteria (an issue template helps) and tag tests with the criterion they prove:

```python
@pytest.mark.req("AC2")
def test_unknown_codes_are_rejected(): ...
```

## Run it locally

```bash
uv sync && npm install
uv run python -m sentinel demo                                # build the demo repo, review its 3 agent PRs
uv run python -m sentinel review --base origin/main --pr-body pr.md --issue-body issue.md
```

Review console (two terminals):

```bash
uv run uvicorn sentinel.api:app --port 8000
```

```bash
npm run dev     # http://localhost:5173, then click "Review demo PRs" or sync a GitHub repo
```

Exit codes: `0` ready, `1` after checks, `2` do not merge. In CI, `--fail-on block|checks|never` picks what fails the job.

---

## How it's built

```
sentinel/
  repo.py              git diff base...head → changed files, added lines, patches
  config.py            [tool.sentinel] + the repo's ruff/mypy config and declared dependencies
  stages/static.py     imports (invented packages/APIs), ruff, mypy, complexity, bandit; added lines only
  stages/integrity.py  tests deleted/skipped/weakened vs. the merge base, secrets, suppressions, gate config
  stages/dynamic.py    the repo's tests in a sandbox copy, changed-line coverage, mutation testing
  stages/requirements.py  acceptance criteria from issue/PR → tests → proven / failing / untested
  ai_review.py         optional Claude review (structured output; can only escalate)
  verdict.py           evidence → ✅ / 🟡 / ⛔ + reviewer checklist
  engine.py            runs the stages, streams events, builds the report
  github.py report.py  PR comment, inline comments, labels
  cli.py api.py        CLI and the review console's backend
web/                   React + TypeScript + Framer Motion review console
demo/                  demo service + three agent PRs (also the end-to-end tests)
action.yml             reusable GitHub Action
```

Sentinel checks itself in CI: ruff, mypy `--strict`, unit tests for every rule, and the three demo PRs end to end.

## Limits

- **Python only.** The verdict model doesn't depend on the language; another language means another set of analyzers
  (for example ESLint, `tsc` and Stryker).
- **Running a PR's tests runs untrusted code.** Sentinel copies the repo into a sandbox directory and strips secrets
  from the environment, but that's process isolation, not a security boundary. For PRs from forks, run without secrets
  or in a locked-down container.
- **Mutation testing is deliberately small** (a few operators, at most 20 mutants on changed lines) so it fits in PR
  time.
- **Tools can't judge design.** That's why every verdict ends with a checklist for the human, and why the human owns
  the merge.
