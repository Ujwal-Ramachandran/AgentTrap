"""Flask + SSE dashboard app (Phase C).

Endpoints:
  GET  /                      the dashboard page
  POST /api/run               start a run; body selects backend/target/cell
  GET  /api/stream/<run_id>   server-sent events for a run (run_start, step, run_end)
  GET  /api/result/<run_id>   the final RunResult, or 202 while still running

Ollama is the default backend for real runs; the page also offers the mock
backend so the dashboard works with no model installed.
"""
from __future__ import annotations

import json

from flask import Flask, Response, jsonify, render_template, request

from agent.config import Budgets, RunConfig
from .broker import RunManager

manager = RunManager()

_DEFAULT_MODEL = {"ollama": "qwen3:8b", "anthropic": "claude-haiku-5-5",
                  "openai": "gpt-4o-mini", "cli": "", "mock": ""}


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.post("/api/run")
    def api_run():
        body = request.get_json(silent=True) or {}
        backend = body.get("backend", "mock")
        cfg = RunConfig(
            backend=backend,
            model=body.get("model") or _DEFAULT_MODEL.get(backend, ""),
            target_kind=body.get("target", "mock"),
            cht_on=bool(body.get("cht_on", False)),
            hardened=bool(body.get("hardened", False)),
            screen_kind=body.get("screen", "mock"),
            budgets=Budgets(max_steps=int(body.get("max_steps", 20))),
        )
        run_id = manager.start_run(cfg)
        return jsonify({"run_id": run_id, "cell": cfg.cell()})

    @app.get("/api/stream/<run_id>")
    def api_stream(run_id: str):
        def gen():
            q = manager.subscribe(run_id)
            try:
                while True:
                    event = q.get()
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") == "run_end":
                        break
            finally:
                manager.unsubscribe(run_id, q)

        return Response(gen(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache",
                                 "X-Accel-Buffering": "no"})

    @app.get("/api/result/<run_id>")
    def api_result(run_id: str):
        res = manager.result(run_id)
        if res is not None:
            return jsonify(res), 200
        return jsonify({"status": "running"}), 202

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, threaded=True, debug=False)
