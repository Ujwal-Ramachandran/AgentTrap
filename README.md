# AgentTrap

AgentTrap is a resilience study of a small, locally run LLM penetration-testing agent. A local LLM agent gets a shell on a sandboxed Linux decoy and tries to root it; the decoy is seeded with Cloak, Honey, Trap deception that targets the agent's own reasoning weaknesses. We then harden the agent (defense-aware prompt plus PromptGuard 2) and measure whether performance recovers. SE6022 Cybersecurity and AI course project. Runs on one RTX 4060 laptop, local and free.

Read CLAUDE.md first. For scope and metrics see PRD.md; for design see ARCHITECTURE.md; for ownership and timeline see TASKS.md.

## Prerequisites

- NVIDIA RTX 4060 (8GB VRAM) or similar, with current NVIDIA drivers and CUDA.
- Ollama, with one attacker model pulled (Qwen3 8B or Llama 3.1 8B, Q4_K_M).
- Python 3.11+ and a container or VM runtime for the decoy host (no network egress).
- PromptGuard 2 weights via LlamaFirewall / PurpleLlama (github.com/meta-llama/PurpleLlama).
- CHT artifact for trap payloads and the CHeaT tool (DOI 10.5281/zenodo.15601739).

## Setup

To be filled in as the build lands. Expected flow: pull the model with Ollama, build the decoy image, install Python dependencies, fetch PromptGuard 2 and the CHT payloads.

## Run the demo

To be filled in. The demo is one screen: the agent's shell console on the left, live metrics on the right. Sequence: plain agent roots the clean host, switch on the CHT traps and watch TSR collapse, the honeytoken flags the bot, harden the agent so PromptGuard 2 catches the injection trap while the deception traps still land, end on the 2x2 and the honest finding. Keep a recorded backup of every step.

## Folder layout

To be created as the build lands. Expected top-level directories: `agent/` (Ollama agent loop), `decoy/` (sandboxed host and seeded files), `traps/` (the five techniques), `harness/` (run N cells, logging), `dashboard/` (Flask + SSE), `results/` (the 2x2 table and charts). The markdown docs (this file, CLAUDE.md, PRD.md, ARCHITECTURE.md, TASKS.md) live at the repo root.

## Team

Ujwal, Bhageerath, Dan, Ivan. See TASKS.md for the split.

## License

See LICENSE. Reused CHT payloads and PromptGuard 2 remain under their own upstream licenses.
