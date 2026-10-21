"""GitHub integration for the Action: read the PR, post the verdict where reviewers already look.

Uses the REST API with the workflow's GITHUB_TOKEN (needs `pull-requests: write` and `issues: write`).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from sentinel.models import PullRequestInfo, Report
from sentinel.report import ICON, INLINE_MARKER, SUMMARY_MARKER, inline_comments, markdown
from sentinel.stages.requirements import linked_issue

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")
LABELS = {"ready": "sentinel: ready", "after_checks": "sentinel: needs-human", "do_not_merge": "sentinel: do-not-merge"}


class GitHub:
    def __init__(self, repo: str, token: str) -> None:
        self.repo, self.token = repo, token

    def call(self, method: str, path: str, body: Any = None) -> Any:
        req = urllib.request.Request(
            f"{API}/repos/{self.repo}{path}", method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
        return json.loads(raw) if raw else None

    def issue_body(self, number: int) -> str | None:
        try:
            return str(self.call("GET", f"/issues/{number}").get("body") or "")
        except urllib.error.HTTPError:
            return None

    def upsert_summary(self, pr: int, body: str) -> None:
        for c in self.call("GET", f"/issues/{pr}/comments?per_page=100"):
            if SUMMARY_MARKER in (c.get("body") or ""):
                self.call("PATCH", f"/issues/comments/{c['id']}", {"body": body})
                return
        self.call("POST", f"/issues/{pr}/comments", {"body": body})

    def replace_inline(self, pr: int, head_sha: str, report: Report) -> int:
        for c in self.call("GET", f"/pulls/{pr}/comments?per_page=100"):
            if INLINE_MARKER in (c.get("body") or ""):
                self.call("DELETE", f"/pulls/comments/{c['id']}")
        comments = inline_comments(report)
        if not comments:
            return 0
        body = f"{INLINE_MARKER}\n{ICON[report.verdict.kind]} Sentinel: {report.verdict.headline}. Line-level findings below."
        try:
            self.call("POST", f"/pulls/{pr}/reviews",
                      {"commit_id": head_sha, "event": "COMMENT", "body": body, "comments": comments})
        except urllib.error.HTTPError as e:  # a line outside the diff makes GitHub reject the whole review
            print(f"::warning::Could not post inline comments: {e.code} {e.read().decode()[:300]}")
            return 0
        return len(comments)

    def set_label(self, pr: int, kind: str) -> None:
        current = {lbl["name"] for lbl in self.call("GET", f"/issues/{pr}/labels")}
        for name in (set(LABELS.values()) & current) - {LABELS[kind]}:
            self.call("DELETE", f"/issues/{pr}/labels/{urllib.parse.quote(name, safe="")}")
        self.call("POST", f"/issues/{pr}/labels", {"labels": [LABELS[kind]]})


def from_event() -> tuple[GitHub, PullRequestInfo, str, str | None, str]:
    """Reads the pull_request event. Returns (client, pr info, pr body, linked issue body, head sha)."""
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    pr = event["pull_request"]
    gh = GitHub(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"])
    body = pr.get("body") or ""
    issue = linked_issue(body)
    info = PullRequestInfo(repo=os.environ["GITHUB_REPOSITORY"], number=pr["number"], title=pr["title"],
                           author=pr["user"]["login"], url=pr["html_url"], base=pr["base"]["sha"],
                           head=pr["head"]["sha"], linked_issue=issue)
    return gh, info, body, gh.issue_body(issue) if issue else None, pr["head"]["sha"]


def publish(gh: GitHub, report: Report, head_sha: str) -> None:
    number = report.pr.number
    if number is None:
        return
    gh.upsert_summary(number, markdown(report))
    posted = gh.replace_inline(number, head_sha, report)
    gh.set_label(number, report.verdict.kind)
    print(f"Posted verdict '{report.verdict.headline}' with {posted} inline comment(s) on #{number}.")
