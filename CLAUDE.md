# CLAUDE.md

Always-on context for AgentTrap. Read this first in every session. For detail, follow the "Where to look" pointers below instead of expanding this file.

## What AgentTrap is

AgentTrap is a resilience study of a small, locally run LLM penetration-testing agent. A local LLM agent gets a shell on a sandboxed Linux decoy host and tries to root it. The host is seeded with Cloak, Honey, Trap (CHT) deception that targets the agent LLM's own reasoning weaknesses. We measure how far the agent is degraded, then harden it with a defense-aware system prompt, quarantine, recovery, and context control. Everything runs on one laptop, free.

## Locked decisions

- Decoy is shell-on-host, a sandboxed Linux container or VM, not a web form. The agent gets a real shell.
- Experiment is a 2x2: CHT off/on by plain/hardened agent, 20 to 50 runs per cell.
- Five seeded techniques: four deception (Cloak T1.1, Honey T3.2, Trap T4.3, Trap T4.1) plus one prompt injection (Trap T5.2). Detailed in PRD.md.
- Two metrics reported together: Task Success Rate (TSR, primary) and Defense Success Rate (DSR). Detailed in PRD.md.

## Hard constraints (non-negotiable)

- One NVIDIA RTX 4060 laptop, 8GB VRAM. One 7 to 8B model at a time (Qwen3 8B or Llama 3.1 8B, Q4).
- Open-source and local first, via Ollama. Everything free. Paid APIs only as an optional, clearly marked fallback.
- Passive defense only: traps, misdirection, honeytokens. Never implement the paper's reverse-shell hack-back (T6.1).
- Fully self-contained: the agent attacks our own decoy on our own machine. No external systems, no network egress from the sandbox.
- Do not use em dashes in any file or output.

## Honest framing

This is a resilience study of a small local agent. It is not a claim that we "defeat AI attackers" or that "modern guardrails are weak." We prove baseline competence first and run a stronger-attacker honesty check.

## Where to look

- PRD.md: problem, goal, course mapping, the 2x2, the five techniques, the three metrics, success criteria, scope, non-goals.
- ARCHITECTURE.md: components and how they connect, the agent loop, model sizing, the Flask-web fallback, sandboxing.
- README.md: prerequisites, setup, how to run the demo, folder layout, team, license.
- TASKS.md: task split by person, milestone timeline, the freeze date, coordination.
- agent/: the pentest agent code (run_agent is the entry point); tests/: mock-based smoke tests.
- Source material: CHT paper (USENIX Security 2025, DOI 10.5281/zenodo.15601739) and PromptGuard 2 / LlamaFirewall (github.com/meta-llama/PurpleLlama).
