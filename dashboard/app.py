"""Flask + SSE dashboard app (Phase C).

Runs a batch of N agent runs and streams the experiment view: live console on the
left, TSR / DSR / GBR on the right, run progress and outcome around them.

Endpoints:
  GET  /                        the dashboard page
  POST /api/run                 start a batch; body selects backend/target/cell/runs
  GET  /api/stream/<batch_id>   server-sent events (run_index, step, run_end, aggregate, batch_end)
  GET  /api/batch/<batch_id>    the latest aggregate, or 202 before the first run finishes
  GET  /api/batches?page=N      paginated batch history, newest first

Ollama is the default backend for real runs; the page also offers the mock
backend so the dashboard works with no model installed.
"""
from __future__ import annotations

import json
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_from_directory

from agent.config import Budgets, RunConfig
from .broker import RunManager

manager = RunManager()

_DEFAULT_MODEL = {"ollama": "qwen3:8b", "anthropic": "claude-haiku-5-5",
                  "openai": "gpt-4o-mini", "cli": "", "mock": ""}

_DECOY_USERS = {
    "agenttrap-decoy": "user1",
}


def create_app() -> Flask:
    app = Flask(__name__)
    sound_dir = Path(__file__).resolve().parents[1] / "assets" / "sound"

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/assets/sound/<path:filename>")
    def asset_sound(filename: str):
        return send_from_directory(sound_dir, filename)

    @app.post("/api/run")
    def api_run():
        body = request.get_json(silent=True) or {}
        backend = body.get("backend", "mock")
        runs = max(1, int(body.get("runs", 20)))
        container = body.get("container", "agenttrap-decoy")
        container_user = body.get("container_user") or _DECOY_USERS.get(
            container, "lowpriv")
        cfg = RunConfig(
            backend=backend,
            model=body.get("model") or _DEFAULT_MODEL.get(backend, ""),
            target_kind=body.get("target", "mock"),
            container=container,
            container_user=container_user,
            reset_cmd=body.get("reset_cmd", ""),
            root_flag=body.get("root_flag", "FLAG{"),
            root_check_cmd=body.get("root_check_cmd", ""),
            root_check_expect=body.get("root_check_expect", "0"),
            cht_on=False,
            hardened=bool(body.get("hardened", False)),
            think=body.get("thinking") == "thinking-on",
            compact_history=bool(body.get("hardened", False)),
            require_root_evidence=bool(body.get("require_root_evidence", False)),
            screen_kind=body.get("screen", "mock"),
            budgets=Budgets(max_steps=int(body.get("max_steps", 40))),
        )
        all_traps = ["T1", "T3", "T4loop", "T4flood", "T5", "HP"]
        selected_traps = body.get("traps", all_traps)
        if selected_traps == "all":
            selected_traps = all_traps
        if (not isinstance(selected_traps, list)
                or not all(trap in all_traps for trap in selected_traps)):
            return jsonify({"error": "invalid trap selection"}), 400
        cfg.cht_on = bool(selected_traps)
        cfg.enabled_traps = selected_traps
        batch_id = manager.start_batch(
            cfg, runs, image=body.get("image") or container,
            seed_script=body.get("seed_script", "seed_traps.sh"),
            enabled_traps=selected_traps)
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

    @app.get("/api/batches")
    def api_batches():
        try:
            page = int(request.args.get("page", 1))
            page_size = int(request.args.get("page_size", 10))
        except ValueError:
            return jsonify({"error": "page and page_size must be integers"}), 400
        if page < 1 or page_size < 1 or page_size > 100:
            return jsonify({"error": "page must be >= 1 and page_size must be 1..100"}), 400
        return jsonify(manager.batches(page, page_size))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, threaded=True, debug=False)
