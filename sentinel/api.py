"""HTTP API for the dashboard. `/api/run` streams pipeline events as NDJSON."""

from __future__ import annotations

import json
import traceback
from collections.abc import Iterator
from pathlib import Path

import anthropic
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from sentinel import gate, llm, pipeline
from sentinel.models import RunRequest
from sentinel.samples import SAMPLES

app = FastAPI(title="Sentinel", version="1.0.0")
WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "ok": True,
        "mode": "live" if llm.is_live() else "replay",
        "model": llm.MODEL if llm.is_live() else None,
        "weights": gate.WEIGHTS,
        "threshold": gate.THRESHOLD,
        "min_coverage": gate.MIN_COVERAGE,
        "min_mutation_score": gate.MIN_MUTATION_SCORE,
    }


@app.get("/api/samples")
def samples() -> list[dict[str, str]]:
    return [s.model_dump() for s in SAMPLES.values()]


@app.post("/api/run")
def run(req: RunRequest) -> StreamingResponse:
    def stream() -> Iterator[str]:
        try:
            for event in pipeline.run(req, pace=0.35):
                yield json.dumps(event) + "\n"
        except anthropic.APIError as e:
            yield json.dumps({"type": "log", "level": "error", "message": f"Claude API error: {e}"}) + "\n"
            yield json.dumps({"type": "done", "passed": False, "iterations": 0}) + "\n"
        except Exception as e:  # noqa: BLE001 — surface engine bugs in the UI instead of a silent hang
            traceback.print_exc()
            yield json.dumps({"type": "log", "level": "error", "message": f"Engine error: {e}"}) + "\n"
            yield json.dumps({"type": "done", "passed": False, "iterations": 0}) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


# Serve the built dashboard (npm run build) from the same origin in production.
if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB_DIST / "index.html")
