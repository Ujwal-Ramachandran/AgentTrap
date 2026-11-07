# Architecture: AgentTrap

See PRD.md for the experiment and metrics, CLAUDE.md for constraints. This file covers how the system is built.

## Components

- **LLM pentest agent**: a Python loop (`agent/`) driving a model through a pluggable backend. Ollama is primary (Qwen3 8B or Llama 3.1 8B, Q4_K_M; local, free). Anthropic, OpenAI, and a Claude Code / Codex CLI backend are optional and paid; see "Model backends" below.
- **Sandboxed decoy host**: a Linux container or VM with no network egress, seeded with the files, logs, and banners that carry the five techniques.
- **Hardening**: a defense-aware system prompt plus quarantine, recovery, and context compaction. These controls are applied only in the hardened half of the 2x2.
- **Flask dashboard** (`dashboard/`): control panel and live view (Flask + server-sent events). It runs a batch of N runs in a background thread and streams each run's events (run_index, step, run_end) plus an aggregate (TSR, DSR, average runtime, outcome, traps) from the loop's `on_event` hook to the browser. Endpoints: `POST /api/run`, `GET /api/stream/<batch_id>`, `GET /api/batch/<batch_id>`. The dashboard is not the target.

## How they connect

The agent issues a shell command to the decoy host. The host runs it and returns output, which in the CHT-on condition is seeded with traps. In the hardened condition, the system prompt and harness recovery controls help the agent handle untrusted output. The agent decides the next command. The run harness repeats this for N runs per 2x2 cell and logs each outcome; the dashboard records and displays each run's TSR, DSR, outcome type, tokens, and time.

## The agent loop

At a high level, one step is: read the latest shell output, decide the next action, run the command, observe the result. The loop ends when the agent roots the host (success), gives up, loops, or hits a step, token, or time budget (failure). If a reply carries no command, the loop reprompts a bounded number of times before giving up, rather than treating stray prose as a surrender. Long command output is head-and-tail truncated before it is fed back. In hardened runs, harness anomaly signals quarantine suspicious sources, deliver a recovery event, and block direct revisits while the agent chooses another investigation path. Consecutive recovery events share a recovery epoch: only the first receives the full directive, while later events use a compact notice to limit context growth. Plain runs retain the original audit-only behavior. `run_agent(config) -> RunResult` is the single entry point the run harness calls.

## Code layout (agent/)

- `loop.py`: `run_agent`, the read-decide-act loop, success / give-up / loop / budget outcomes.
- `config.py`: `RunConfig` and `Budgets` (backend, 2x2 cell, budgets, success condition).
- `llm.py`: the backend interface and the Ollama, Anthropic, OpenAI, CLI, and mock backends.
- `targets.py`: the `Target` seam, `DockerExecTarget` (one persistent `docker exec` shell, so working directory, environment, and gained privilege persist across commands) and `MockTarget`.
- `screen.py`: optional input-screen implementations.
- `prompts.py`: the plain and defense-aware system prompts.
- `results.py`: `RunResult`, `StepRecord`, JSONL logging (Q4, Q5).
- `run.py`: the CLI wrapper. `tests/`: unittest suites and smoke tests (no GPU, no Docker).
- `dashboard/`: the Flask + SSE app (`app.py`), the run manager and event broker (`broker.py`), and the page (`templates/index.html`).

## Model backends

The loop talks to the model through one interface (`chat(messages) -> ChatReply`), so the backend is swappable. Ollama is the default and the only one used for the headline 2x2. The hosted backends (Anthropic, OpenAI) and the CLI backend (Claude Code or Codex in non-interactive print mode) are optional, may cost money, and reach the network; they are meant for the stronger-attacker honesty check and for machines without Ollama, not for the main experiment. A dependency-free mock backend drives the loop in tests and plumbing demos (`--backend mock`). Per-call limits are enforced inside the call, not just between steps: Ollama caps generation with `num_predict` and streams so it can stop when the per-call time cap is hit, and the hosted backends cap with `max_tokens` (all set from `Budgets`). The decoy sandbox stays no-egress regardless; only the agent process reaches a hosted API.

## Tech choices and 4060 sizing

- One 7 to 8B model at a time, Q4_K_M, about 5GB VRAM, well within 8GB. Never load two large models together.
- Attacker agent, decoy host, and dashboard are all light.
- LlamaFirewall's AlignmentCheck scanner needs a 70B-class model and is not used.

## Fallback (documented)

If the shell-on-host setup stalls in week 1, drop to a Flask-web decoy: the agent attacks over HTTP and the file-based traps (symlink loop, honeytoken) are simulated in page content instead of on a real filesystem. Less impressive, but the project still stands. The 2x2, metrics, and techniques are unchanged; only the decoy substrate changes.

## Safety and sandboxing

Self-contained by design: the agent attacks our own decoy on our own machine. No external systems, no network egress from the sandbox. Passive defense only (traps, misdirection, honeytokens); the reverse-shell hack-back (T6.1) is out of scope for legal and ethical reasons. Base payloads and the CHeaT trap-insertion tool come from the CHT artifact (DOI 10.5281/zenodo.15601739), wired into the decoy host.
