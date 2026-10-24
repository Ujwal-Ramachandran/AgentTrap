# AgentTrap

AgentTrap is a resilience study of a small, locally run LLM penetration-testing agent. A local LLM agent gets a shell on a sandboxed Linux decoy and tries to root it; the decoy is seeded with Cloak, Honey, Trap deception that targets the agent's own reasoning weaknesses. We then harden the agent (defense-aware prompt plus PromptGuard 2) and measure whether performance recovers. SE6022 Cybersecurity and AI course project. Runs on one RTX 4060 laptop, local and free.

Read CLAUDE.md first. For scope and metrics see PRD.md; for design see ARCHITECTURE.md; for ownership and timeline see TASKS.md.

## Prerequisites

- Python 3.10+ (the loop runs on the standard library alone with the mock backend).
- NVIDIA RTX 4060 (8GB VRAM) or similar, with current NVIDIA drivers and CUDA, for the real model.
- Ollama (primary backend), with one attacker model pulled (Qwen3 8B or Llama 3.1 8B, Q4_K_M).
- Optional backends: an Anthropic or OpenAI API key, or the Claude Code / Codex CLI, for the honesty check or machines without Ollama.
- A container or VM runtime for the decoy host (no network egress).
- PromptGuard 2 weights via LlamaFirewall / PurpleLlama (github.com/meta-llama/PurpleLlama); gated on Hugging Face.
- CHT artifact for trap payloads and the CHeaT tool (DOI 10.5281/zenodo.15601739).

## Setup

```
pip install -r requirements.txt          # ollama client; uncomment extras as needed
python tests/test_loop_smoke.py          # verify the loop with no GPU or Docker
python tests/test_hardening_smoke.py     # verify input screening
```

For real runs: install and start Ollama, then `ollama pull qwen3:8b` (or `llama3.1:8b`). The decoy image, PromptGuard 2 weights, and CHT payloads land as those parts of the build complete.

## Run the agent

```
# quick mock run, no model needed
python -m agent.run --target mock

# real run against the decoy (primary backend)
python -m agent.run --backend ollama --model qwen3:8b --target docker --container agenttrap-decoy

# hardened agent (defense-aware prompt + PromptGuard 2 screening)
python -m agent.run --target docker --hardened

# optional non-Ollama backends (paid / network)
python -m agent.run --backend anthropic --model claude-sonnet-5-5 --target docker
python -m agent.run --backend cli --target docker   # uses the Claude Code / Codex CLI
```

Each run prints a `RunResult` and writes a JSONL transcript under `results/logs/`. The demo view (agent console left, live metrics right) is the Flask dashboard, built in a later phase.

## Folder layout

- `agent/` (the pentest agent: loop, backends, targets, screening, prompts, results, CLI)
- `tests/` (mock-based smoke tests)
- `results/` (per-run JSONL logs and the runs summary; git-ignored)
- Planned by the decoy and harness owners: `decoy/`, `traps/`, `harness/`, `dashboard/`.
- The markdown docs (this file, CLAUDE.md, PRD.md, ARCHITECTURE.md, TASKS.md) live at the repo root.

## Team

Ujwal, Bhageerath, Dan, Ivan. See TASKS.md for the split.

## License

See LICENSE. Reused CHT payloads and PromptGuard 2 remain under their own upstream licenses.
