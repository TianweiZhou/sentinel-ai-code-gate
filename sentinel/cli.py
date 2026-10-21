"""Command line: review a branch locally, or run inside GitHub Actions on a pull request.

    sentinel review --base origin/main --pr-body pr.md --issue-body issue.md
    sentinel review --github          # inside the Action: reads the PR event and posts the verdict
    sentinel demo                     # builds the demo repo and reviews its three agent PRs

Exit code: 0 ready, 1 merge after checks, 2 do not merge (see --fail-on for CI).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from sentinel import demo, engine, store
from sentinel.models import PullRequestInfo, Report
from sentinel.report import markdown, terminal
from sentinel.stages.requirements import linked_issue

_ICON = {"pass": "\033[32m✔", "warn": "\033[33m▲", "fail": "\033[31m✖", "skipped": "\033[90m·"}
_EXIT = {"ready": 0, "after_checks": 1, "do_not_merge": 2}


def _run(root: Path, base: str, head: str, pr: PullRequestInfo, pr_body: str, issue_body: str | None,
         use_ai: bool | None, quiet: bool = False) -> Report:
    report: Report | None = None
    for event in engine.review(root, base, head, pr=pr, pr_body=pr_body, issue_body=issue_body, use_ai=use_ai):
        if event["type"] == "stage" and event["status"] != "running" and not quiet:
            print(f"  {_ICON[event['status']]} {event['stage']:<13}\033[0m {event.get('summary', '')}")
        elif event["type"] == "report":
            report = Report.model_validate(event["report"])
    assert report is not None
    return report


def _review(args: argparse.Namespace) -> int:
    root = Path(args.repo).resolve()
    if args.github:
        from sentinel import github  # only needed inside Actions

        gh, pr, pr_body, issue_body, head_sha = github.from_event()
        base, head = pr.base, pr.head
    else:
        pr_body = Path(args.pr_body).read_text() if args.pr_body else ""
        issue_body = Path(args.issue_body).read_text() if args.issue_body else None
        base, head = args.base, args.head
        branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", head], cwd=root, capture_output=True,
                                text=True, check=False).stdout.strip()
        pr = PullRequestInfo(repo=args.name or root.name, title=args.title or branch or "Local review", base=base,
                             head=head, linked_issue=linked_issue(pr_body), number=args.number)

    print(f"\033[1mSentinel reviewing {pr.title}\033[0m ({base}...{head})")
    report = _run(root, base, head, pr, pr_body, issue_body, False if args.no_ai else None)
    print(terminal(report))

    if args.json:
        Path(args.json).write_text(report.model_dump_json(indent=2))
    if args.markdown:
        Path(args.markdown).write_text(markdown(report))
    if args.save:
        print(f"Saved for the review console: {store.save(report)}")
    if args.github:
        github.publish(gh, report, head_sha)
        if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(summary, "a") as f:
                f.write(markdown(report))
        if out := os.environ.get("GITHUB_OUTPUT"):
            with open(out, "a") as f:
                f.write(f"verdict={report.verdict.kind}\nscore={report.overall}\n")

    code = _EXIT[report.verdict.kind]
    threshold = {"block": 2, "checks": 1, "never": 3}[args.fail_on]
    return code if code >= threshold else 0


def _demo(args: argparse.Namespace) -> int:
    target = Path(args.dir or Path(tempfile.gettempdir()) / "sentinel-demo-service")
    scenarios = demo.build(target)
    print(f"Built demo repo at {target} with {len(scenarios)} agent PR branches.\n")
    for i, sc in enumerate(scenarios, start=1):
        subprocess.run(["git", "checkout", "-q", sc.branch], cwd=target, check=True)
        pr = PullRequestInfo(repo="sentinel-demo-service", number=i, title=sc.title, author="coding-agent",
                             base="main", head=sc.branch, linked_issue=sc.issue_number)
        print(f"\033[1m#{i} {sc.title}\033[0m  ({sc.branch})")
        report = _run(target, "main", "HEAD", pr, sc.pr_body, sc.issue_body, False if args.no_ai else None,
                      quiet=True)
        print(terminal(report).split("\n  Reviewer checklist")[0] + "\n")
        store.save(report)
    subprocess.run(["git", "checkout", "-q", "main"], cwd=target, check=True)
    print(f"Reports saved to {store.reports_dir()} — open the review console to explore them.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sentinel", description="Merge-readiness review for agent-written pull requests.")
    sub = parser.add_subparsers(dest="command", required=True)

    r = sub.add_parser("review", help="review the changes between --base and --head")
    r.add_argument("--repo", default=".", help="repository root (default: current directory)")
    r.add_argument("--base", default="origin/main", help="branch or commit the PR merges into")
    r.add_argument("--head", default="HEAD")
    r.add_argument("--pr-body", help="file with the PR description (may contain `Closes #N` and AC items)")
    r.add_argument("--issue-body", help="file with the linked issue (its AC1/AC2… items are the contract)")
    r.add_argument("--title")
    r.add_argument("--name", help="repository name shown in the console")
    r.add_argument("--number", type=int, help="PR number shown in the console")
    r.add_argument("--json", help="write the full report as JSON")
    r.add_argument("--markdown", help="write the PR comment as Markdown")
    r.add_argument("--save", action="store_true", help="store the report for the review console")
    r.add_argument("--github", action="store_true", help="inside GitHub Actions: read the PR event and post results")
    r.add_argument("--no-ai", action="store_true", help="skip the AI reviewer even if ANTHROPIC_API_KEY is set")
    r.add_argument("--fail-on", choices=["block", "checks", "never"], default="block",
                   help="non-zero exit when the verdict is at least this bad (default: block = ⛔ only)")
    r.set_defaults(fn=_review)

    d = sub.add_parser("demo", help="build the demo repo and review its three agent PRs")
    d.add_argument("--dir", help="where to build the demo repo")
    d.add_argument("--no-ai", action="store_true")
    d.set_defaults(fn=_demo)

    args = parser.parse_args(argv)
    result: int = args.fn(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
