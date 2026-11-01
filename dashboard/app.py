"""Flask + SSE dashboard app (Phase C).

Runs a batch of N agent runs and streams the experiment view: live console on the
left, TSR / DSR / GBR on the right, run progress and outcome around them.

Endpoints:
  GET  /                        the dashboard page
  POST /api/run                 start a batch; body selects backend/target/cell/runs
  GET  /api/stream/<batch_id>   server-sent events (run_index, step, run_end, aggregate, batch_end)
  GET  /api/batch/<batch_id>    the latest aggregate, or 202 before the first run finishes

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
        runs = max(1, int(body.get("runs", 20)))
        cfg = RunConfig(
            backend=backend,
            model=body.get("model") or _DEFAULT_MODEL.get(backend, ""),
            target_kind=body.get("target", "mock"),
            container=body.get("container", "agenttrap-decoy"),
            container_user=body.get("container_user", "lowpriv"),
            reset_cmd=body.get("reset_cmd", ""),
            root_flag=body.get("root_flag", "FLAG{"),
            root_check_cmd=body.get("root_check_cmd", ""),
            root_check_expect=body.get("root_check_expect", "0"),
            cht_on=bool(body.get("cht_on", False)),
            hardened=bool(body.get("hardened", False)),
            compact_history=bool(body.get("hardened", False)),
            require_root_evidence=bool(body.get("require_root_evidence", False)),
            screen_kind=body.get("screen", "mock"),
            budgets=Budgets(max_steps=int(body.get("max_steps", 20))),
        )
        batch_id = manager.start_batch(
            cfg, runs, image=body.get("image", "agenttrap-decoy"),
            seed_script=body.get("seed_script", "seed_traps.sh"))
        return jsonify({"batch_id": batch_id, "total": runs,
                        "model": cfg.model or backend, "cht_on": cfg.cht_on,
                        "hardened": cfg.hardened})

    @app.get("/api/stream/<batch_id>")
    def api_stream(batch_id: str):
        def gen():
            q = manager.subscribe(batch_id)
            try:
                while True:
                    event = q.get()
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") == "batch_end":
                        break
            finally:
                manager.unsubscribe(batch_id, q)

        return Response(gen(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/batch/<batch_id>")
    def api_batch(batch_id: str):
        agg = manager.aggregate(batch_id)
        if agg is not None:
            return jsonify(agg), 200
        return jsonify({"status": "running"}), 202

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, threaded=True, debug=False)
