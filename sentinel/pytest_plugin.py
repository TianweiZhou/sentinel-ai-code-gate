"""pytest plugin loaded into the target repo's test run (`-p sentinel.pytest_plugin`).

Registers the `req` marker and writes one JSON record per test, including which
acceptance criteria it verifies, to the file named by $SENTINEL_RESULTS.
"""

from __future__ import annotations

import json
import os
from collections.abc import Generator
from typing import Any

import pytest

_results: list[dict[str, Any]] = []


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "req(*ids): acceptance criteria this test verifies, e.g. req('AC1')")


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    report = yield
    if report.when == "call" or (report.when == "setup" and (report.failed or report.skipped)):
        message = None
        if report.failed:
            crash = getattr(report.longrepr, "reprcrash", None)
            message = crash.message if crash else str(report.longrepr)[-500:]
        _results.append({
            "nodeid": item.nodeid,
            "requirement_ids": [str(a) for m in item.iter_markers("req") for a in m.args],
            "passed": report.passed,
            "message": message if not report.skipped else "skipped",
            "duration_ms": report.duration * 1000,
        })
    return report


def pytest_sessionfinish(session: pytest.Session) -> None:
    path = os.environ.get("SENTINEL_RESULTS")
    if path:
        with open(path, "w") as f:
            json.dump(_results, f)
