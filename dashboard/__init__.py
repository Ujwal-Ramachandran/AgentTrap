"""AgentTrap dashboard (Phase C): Flask + server-sent events.

Live agent console on the left, metrics on the right. The dashboard launches
runs and streams their events; it is a control panel, not the target (see
ARCHITECTURE.md). create_app() builds the Flask app; RunManager runs agents in
background threads and fans their events out to SSE subscribers.
"""
from .app import create_app
from .broker import RunManager

__all__ = ["create_app", "RunManager"]
