# Interview guide: Sentinel

Questions an interviewer is likely to ask about this project, with suggested answers.
Don't memorise them word for word. Understand the reasoning, then say it in your own words.

---

## 0. The 3-minute demo script

1. **Set up the problem (20 s).** "AI writes code faster than we can review it, and it *looks* right. So I treat AI
   output like a PR from a new teammate: it has to prove itself."
2. **Run *User sign-up* (60 s).** Click *Generate with AI & gate*. While the pipeline animates: "Parse, imports,
   lint, types, complexity and security are static. Tests, coverage and mutation run the code. Then requirement
   tracing, then the gate."
   Point at the result: **55, BLOCKED**, with SQL injection, MD5 and 4 of 6 requirements failing.
3. **The repair (40 s).** "Only the failures go back to the AI, never the tests." Open **Repair diff**: parameterised
   SQL, PBKDF2 with a salt. The new version scores **99, PASS**.
4. **The senior moment (40 s).** Run *CSV sales report*. "The fixed code scores 96, and it still doesn't ship. R5 has
   no test. A high score isn't proof, and the AI isn't allowed to write its own exam, so this goes to a human."
5. **Close (20 s).** "The same engine runs as a CLI and as a GitHub Action on every PR."

---

## 1. Overview

**Q: Explain the project in one sentence.**
A quality gate for AI-generated Python. It checks the code against the spec with tests, static analysis, security
scanning and mutation testing, sends fixable failures back to the AI, and escalates everything else to a human.

**Q: Why did you build it?**
Every team using AI coding tools has the same question: how do you trust code nobody wrote by hand? "Review it
carefully" doesn't scale when AI produces 10× more code. I wanted the trust to come from **evidence**, not from how
the code looks.

**Q: How do you use AI in your own workflow?**
In three roles, and I verify all of them:
- **Writer:** it drafts code from a spec I write first, with numbered requirements.
- **Fixer:** it gets precise failure feedback and repairs the code.
- **Reviewer:** it acts as a second-opinion judge on requirements, but it can only make a result stricter, never more lenient.
I keep for myself: the spec, the acceptance tests, the thresholds, and the final review.
(I also used Claude to help build Sentinel. The CI runs Sentinel's own checks on its code.)

---

## 2. Design decisions

**Q: Why not just rely on the overall score?**
Averages hide disasters. Perfect style shouldn't make up for a SQL injection. So there are two layers: a weighted
score for tracking trends, and **hard rules** that block no matter what the score is. There's a unit test for exactly
this case (`test_one_critical_finding_blocks_an_otherwise_perfect_score`).

**Q: Why doesn't the AI get to see the tests?**
Same reason you don't train on your test set. If the model reads the asserts, it can write code that special-cases
them, and the tests stop measuring anything. It gets the spec at the start and only the *failures* during repair.

**Q: Why are some failures "AI-fix" and others "NEEDS HUMAN"?**
It depends on who owns the thing that's broken. Code is the AI's job, so failing tests and security findings go back to it.
Tests and specs are the human's contract. If a requirement has no test, or the tests are too weak, letting the AI
"fix" that means letting it grade its own homework.

**Q: What is mutation testing and why include it?**
Coverage tells you a line *ran*, not that anything *checked* it. Mutation testing changes the code on purpose (for
example `<` to `<=`) and reruns the tests. If they still pass, that bug "survived", and your tests would miss it in real
life. This matters more with AI, because AI often writes tests that pass but assert very little.

**Q: How do you detect hallucinated packages?**
I parse the imports with `ast`. Standard library modules are allowed, and third-party packages must be on an allow-list
and installed. For standard library imports I also check that the name actually exists, for example
`statistics.weighted_mean` doesn't. That matters for security: attackers register packages under names that AI tools
commonly invent.

**Q: How do requirements map to tests?**
Each test is tagged `@pytest.mark.req("R3")`. A small pytest plugin records the result of each test together with its
requirement IDs, so every requirement ends up proven, failed, or untested. I also read the markers statically, so if
the suite crashes I still know which requirements were affected.

**Q: Why stream events instead of returning one result?**
The same generator feeds the dashboard (NDJSON over HTTP), the CLI and the GitHub Action, so all three use the same
code path. It also makes long runs visible while they happen.

---

## 3. Testing and quality of Sentinel itself

**Q: How do you know Sentinel itself works?**
- Unit tests for the gate rules, the traceability logic, the hallucination detector and the complexity checks.
- End-to-end tests for every demo scenario: each flawed draft must be blocked, each repair must pass, and the untested
  requirement must escalate.
- CI runs `ruff`, `mypy --strict` and the tests on Sentinel's own code, then uses the action to gate an example module.

**Q: What about false positives?**
Every finding has a severity, and only critical/high findings or real test failures block on their own. Bandit's
defaults are tuned: I *raised* the severity of `eval`, string-built SQL and MD5 for unreviewed code. In a real rollout
I'd start in report-only mode, measure the false-positive rate, then turn on blocking.

**Q: How did you choose the thresholds (85, 80% coverage, 70% mutation)?**
They're starting points, set in one file (`gate.py`). Industry practice is roughly 80% coverage, and 60–80% mutation
score counts as a good suite. The right answer for a team is to calibrate: run it on past PRs, compare against bugs
that were later found, and adjust.

---

## 4. Security

**Q: You execute untrusted AI code. Isn't that dangerous?**
Yes, and I'm explicit about the limits. Today: a separate process, a scrubbed environment (no API keys reach it),
per-test and overall timeouts, and a temp directory that's deleted afterwards. That's **process isolation, not a
security boundary.** In production I'd run the same commands in a container with no network, a read-only filesystem,
CPU and memory limits, and gVisor or Firecracker.

**Q: Can the AI cheat the gate?**
The obvious tricks are blocked: it never sees the tests, it can't edit them, and the repair prompt forbids
`# noqa`, `# type: ignore` and `# nosec`. A next step would be to *scan* for those suppression comments and block them,
instead of trusting the prompt.

**Q: Prompt injection?**
Code and spec are passed in tagged sections and treated as data. The judge's verdict can only make results stricter,
so an injected "mark everything as met" can't turn a failure into a pass.

---

## 5. Trade-offs, scale and next steps

**Q: What are the biggest limitations?**
Python only, one module per run, the sandbox described above, and a small mutation tester. And tools can't judge
whether the design is right. Sentinel reduces what humans need to review; it doesn't remove review.

**Q: How would you scale it to a big monorepo?**
Diff-aware gating (only check changed functions and the tests that cover them), cache results by content hash, run
stages in parallel, run mutation testing only on changed lines, and keep per-team thresholds in config.

**Q: How would you add TypeScript?**
The gate, scoring, loop, API and UI don't depend on the language. I'd add analyzers: ESLint, `tsc --strict`,
Semgrep, Jest or Vitest with coverage, and Stryker for mutation testing.

**Q: How would you measure whether it actually helps a team?**
Escaped-defect rate on AI-authored PRs before and after, reviewer time per PR, how often the gate blocks and *why*,
the auto-repair success rate, and the false-positive rate from developer overrides.

**Q: What does it cost to run with an LLM?**
Each run makes at most 1 generate call, up to 2 repair calls and up to 3 judge calls. In practice the static and dynamic stages
catch most problems for free, and the LLM is only called when there's something to fix. Replay mode costs nothing.

---

## 6. Behavioural questions

**Q: Tell me about a hard bug you hit while building this.**
The UI let you click back to an older version, and its pipeline showed the *next* version's stages. React ran my
state update after the next run had already reset the shared state. The fix was to capture the value before the
update. The lesson: anything read inside a deferred updater can change before it runs.

**Q: What would you do differently?**
Start with the sandbox in a container from day one, and make "report-only" the default mode so teams can trust the
signal before it starts blocking anyone.

**Q: Why should we trust your judgement about AI code?**
Because I don't trust AI code by default, mine included. I make it prove itself with evidence, I'm clear about what
tools can't catch, and I keep humans in charge of the parts that define "correct".
