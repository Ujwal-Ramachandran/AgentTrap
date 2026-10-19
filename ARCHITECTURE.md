# Architecture: AgentTrap

See PRD.md for the experiment and metrics, CLAUDE.md for constraints. This file covers how the system is built.

## Components

- **LLM pentest agent**: a Python loop driving a local model served by Ollama (Qwen3 8B or Llama 3.1 8B, Q4_K_M).
- **Sandboxed decoy host**: a Linux container or VM with no network egress, seeded with the files, logs, and banners that carry the five techniques.
- **Hardening**: a defense-aware system prompt plus PromptGuard 2 (22M or 86M DeBERTa) screening the agent's inputs. Applied only in the hardened half of the 2x2.
- **Flask dashboard**: control panel and live view (Flask + server-sent events). The dashboard is not the target.

## How they connect

The agent issues a shell command to the decoy host. The host runs it and returns output, which in the CHT-on condition is seeded with traps. In the hardened condition, PromptGuard 2 screens that returned output before it reaches the model. The agent decides the next command. The run harness repeats this for N runs per 2x2 cell and logs each outcome; the dashboard records and displays each run's TSR, DSR, GBR, outcome type, tokens, and time.

## The agent loop

At a high level, one step is: read the latest shell output, decide the next action, run the command, observe the result. The loop ends when the agent roots the host (success), gives up, or hits a step or token budget (failure). The hardened agent adds an input-screening step (PromptGuard 2) and a defense-aware system prompt; it does not change itself mid-run.

## Tech choices and 4060 sizing

- One 7 to 8B model at a time, Q4_K_M, about 5GB VRAM, well within 8GB. Never load two large models together.
- PromptGuard 2 is small (about 90 to 350MB) and runs alongside the attacker model.
- Attacker agent, decoy host, and dashboard are all light.
- LlamaFirewall's AlignmentCheck scanner needs a 70B-class model and is not used. If ever wanted, it is an optional paid API extension (about $4 max). Team decision: PromptGuard 2 only.

## Fallback (documented)

If the shell-on-host setup stalls in week 1, drop to a Flask-web decoy: the agent attacks over HTTP and the file-based traps (symlink loop, honeytoken) are simulated in page content instead of on a real filesystem. Less impressive, but the project still stands. The 2x2, metrics, and techniques are unchanged; only the decoy substrate changes.

## Safety and sandboxing

Self-contained by design: the agent attacks our own decoy on our own machine. No external systems, no network egress from the sandbox. Passive defense only (traps, misdirection, honeytokens); the reverse-shell hack-back (T6.1) is out of scope for legal and ethical reasons. Base payloads and the CHeaT trap-insertion tool come from the CHT artifact (DOI 10.5281/zenodo.15601739), wired into the decoy host.
