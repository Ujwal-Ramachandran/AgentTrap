"""In-memory event broker and run manager for the dashboard.

Runs execute in background threads; each emits events (run_start, step, run_end)
through the agent's on_event hook. The broker keeps a per-run history so a late
subscriber catches up, and fans new events out to live SSE subscribers. State is
in-memory and per-process, which is all the single-operator demo needs.
"""
from __future__ import annotations

import queue
import threading

from agent.config import RunConfig
from agent.loop import run_agent


class RunManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._history: dict[str, list[dict]] = {}
        self._subscribers: dict[str, list[queue.Queue]] = {}
        self._results: dict[str, dict] = {}

    def _publish(self, run_id: str, event: dict) -> None:
        with self._lock:
            self._history.setdefault(run_id, []).append(event)
            if event.get("type") == "run_end":
                self._results[run_id] = event
            subs = list(self._subscribers.get(run_id, []))
        for q in subs:
            q.put(event)

    def subscribe(self, run_id: str) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self._lock:
            self._subscribers.setdefault(run_id, []).append(q)
            backlog = list(self._history.get(run_id, []))
        for event in backlog:
            q.put(event)
        return q

    def unsubscribe(self, run_id: str, q: queue.Queue) -> None:
        with self._lock:
            subs = self._subscribers.get(run_id, [])
            if q in subs:
                subs.remove(q)

    def result(self, run_id: str) -> dict | None:
        with self._lock:
            return self._results.get(run_id)

    def start_run(self, config: RunConfig) -> str:
        run_id = config.run_id

        def worker() -> None:
            run_agent(config, on_event=lambda e: self._publish(run_id, e))

        threading.Thread(target=worker, daemon=True).start()
        return run_id
