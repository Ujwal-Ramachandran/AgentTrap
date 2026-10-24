"""AgentTrap pentest agent package (Ujwal's component).

run_agent(config) in agent.loop is the single entry point the run harness
calls. See ARCHITECTURE.md for the loop and CLAUDE.md for project constraints.
"""
from .config import RunConfig, Budgets
from .results import RunResult, StepRecord
from .loop import run_agent

__all__ = ["RunConfig", "Budgets", "RunResult", "StepRecord", "run_agent"]
