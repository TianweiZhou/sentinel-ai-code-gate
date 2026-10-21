"""Backend for the review console: the senior's queue of PR verdicts across repositories.

    GET  /api/reports           queue (one row per PR)
    GET  /api/reports/{id}      full report
    POST /api/demo              build the demo repo and review its agent PRs live (NDJSON stream)
    POST /api/review            review a local branch live (NDJSON stream)
    POST /api/sync              pull the latest Sentinel reports of a GitHub repo's open PRs (uses the `gh` CLI)
"""

from __future__ import annotations

import io
import json
import subprocess
import tempfile
import traceback
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from sentinel import ai_review, demo, engine, store
from sentinel.models import PullRequestInfo, Report

app = FastAPI(title="Sentinel review console", version="2.0.0")
WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
PACE = 0.25  # seconds per stage, so the console can animate progress


def _summary(r: Report) -> dict[str, Any]:
    return {"id": r.id, "repo": r.pr.repo, "number": r.pr.number, "title": r.pr.title, "author": r.pr.author,
            "url": r.pr.url, "verdict": r.verdict.kind, "overall": r.overall, "created_at": r.created_at,
            "blockers": len(r.verdict.blockers), "checks": len(r.verdict.checks)}


def _line(event: dict[str, Any]) -> str:
    return json.dumps(event) + "\n"


def _stream(events: Iterator[dict[str, Any]]) -> StreamingResponse:
    def guarded() -> Iterator[str]:
        try:
            for e in events:
                yield _line(e)
        except Exception as e:  # noqa: BLE001 — show engine errors in the console instead of a silent hang
            traceback.print_exc()
            yield _line({"type": "error", "message": str(e)})
        yield _line({"type": "done"})

    return StreamingResponse(guarded(), media_type="application/x-ndjson")


def _review_and_save(root: Path, base: str, pr: PullRequestInfo, pr_body: str,
                     issue_body: str | None) -> Iterator[dict[str, Any]]:
    for event in engine.review(root, base, "HEAD", pr=pr, pr_body=pr_body, issue_body=issue_body, pace=PACE):
        if event["type"] == "report":
            report = Report.model_validate(event["report"])
            store.save(report)
            event = {"type": "report", "report": report.model_dump(), "summary": _summary(report)}
        yield event


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "ai_reviewer": ai_review.enabled(), "model": ai_review.MODEL if ai_review.enabled() else None,
            "reports_dir": str(store.reports_dir())}


@app.get("/api/reports")
def reports() -> list[dict[str, Any]]:
    return [_summary(r) for r in store.load_all()]


@app.get("/api/reports/{report_id}")
def report(report_id: str) -> dict[str, Any]:
    for r in store.load_all():
        if r.id == report_id:
            return r.model_dump()
    raise HTTPException(404, "report not found")


@app.post("/api/demo")
def run_demo() -> StreamingResponse:
    def events() -> Iterator[dict[str, Any]]:
        target = Path(tempfile.gettempdir()) / "sentinel-demo-service"
        scenarios = demo.build(target)
        for i, sc in enumerate(scenarios, start=1):
            subprocess.run(["git", "checkout", "-q", sc.branch], cwd=target, check=True)
            pr = PullRequestInfo(repo="sentinel-demo-service (local)", number=i, title=sc.title, author="coding-agent",
                                 base="main", head=sc.branch, linked_issue=sc.issue_number)
            yield {"type": "pr", "index": i, "total": len(scenarios), "title": sc.title, "branch": sc.branch}
            yield from _review_and_save(target, "main", pr, sc.pr_body, sc.issue_body)
        subprocess.run(["git", "checkout", "-q", "main"], cwd=target, check=True)

    return _stream(events())


class LocalReview(BaseModel):
    path: str
    base: str = "main"
    title: str | None = None
    pr_body: str = ""
    issue_body: str | None = None


@app.post("/api/review")
def run_review(req: LocalReview) -> StreamingResponse:
    root = Path(req.path).expanduser()
    if not (root / ".git").exists():
        raise HTTPException(400, f"{root} is not a git repository")
    pr = PullRequestInfo(repo=root.name, title=req.title or "Local branch", base=req.base, head="HEAD")
    return _stream(_review_and_save(root, req.base, pr, req.pr_body, req.issue_body))


class Sync(BaseModel):
    repo: str  # owner/name


def _gh(*args: str) -> bytes:
    proc = subprocess.run(["gh", *args], capture_output=True, check=False)
    if proc.returncode != 0:
        raise HTTPException(502, f"gh {' '.join(args[:2])} failed: {proc.stderr.decode()[:300]}")
    return proc.stdout


@app.post("/api/sync")
def sync(req: Sync) -> dict[str, Any]:
    """For each open PR, download the `sentinel-report` artifact from its newest workflow run."""
    prs = json.loads(_gh("pr", "list", "--repo", req.repo, "--state", "open", "--json", "number,headRefName"))
    imported = 0
    for pr in prs:
        runs = json.loads(_gh("api", f"repos/{req.repo}/actions/runs?branch={pr['headRefName']}&per_page=5"))
        for run in runs.get("workflow_runs", []):
            arts = json.loads(_gh("api", f"repos/{req.repo}/actions/runs/{run['id']}/artifacts"))
            art = next((a for a in arts.get("artifacts", []) if a["name"] == "sentinel-report" and not a["expired"]), None)
            if not art:
                continue
            blob = _gh("api", f"repos/{req.repo}/actions/artifacts/{art['id']}/zip")
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                store.save(Report.model_validate_json(z.read("sentinel-report.json")))
            imported += 1
            break
    return {"open_prs": len(prs), "imported": imported}


if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB_DIST / "index.html")
