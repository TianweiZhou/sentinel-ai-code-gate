"""Where finished reports live, so the review console can list them across repositories."""

from __future__ import annotations

import os
from pathlib import Path

from sentinel.models import Report


def reports_dir() -> Path:
    d = Path(os.environ.get("SENTINEL_REPORTS", Path.home() / ".sentinel" / "reports")).expanduser()
    d.mkdir(parents=True, exist_ok=True)
    return d


def save(report: Report) -> Path:
    """One file per PR: a re-run replaces the previous verdict for that PR."""
    key = report.id.rsplit("__", 1)[0] if report.pr.number else report.id
    path = reports_dir() / f"{key}.json"
    path.write_text(report.model_dump_json(indent=2))
    return path


def load_all() -> list[Report]:
    reports = []
    for p in reports_dir().glob("*.json"):
        try:
            reports.append(Report.model_validate_json(p.read_text()))
        except ValueError:
            continue
    return sorted(reports, key=lambda r: r.created_at, reverse=True)
