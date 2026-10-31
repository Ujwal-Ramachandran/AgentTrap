# AgentTrap, integration changelog (`ujwal/integration`)

This branch reconciles three independently diverged lines of work onto `main`:
`main` (agent core + Bhageeratha + Dan's suid decoy), Dan's `dan/decoy_cloak_honey`
(agent robustness + new decoys + live terminal), and `ujwal/e2e` (the measurement
layer: traps, harness, metrics, dashboard, decoy). All three branched from the
same point (the agent-core merge), so the two agent cores were merged by hand.

Backup: `ujwal/e2e` is untouched on the remote. Nothing here has been pushed to
`main`.

## Folded in from Dan (`dan/decoy_cloak_honey`), merged clean onto main
- Binary-mode persistent shell in `targets.py` (bufsize=0, bytes I/O) that
  removes the need for the Windows CRLF/encoding workarounds at the source.
- Deterministic observation + failure ledgers, bounded request context, and
  method-family tracking in `loop.py`.
- A think-disabled fallback: when the model spends its whole generation on hidden
  reasoning and returns no command, retry once with `think=False`.
- `think` flag threaded through every LLM backend in `llm.py`.
- New decoys: `sudo_find`, `cron_writable_copy`, `cron_writable_suid_shell`,
  `bhageeratha_decoy` (each with its own `run_decoy.py`).
- `tools/live_terminal.py` (CLI transcript tailer) and `run.py --no-live`.
- Stricter prompt rules in `prompts.py` and a stricter command parser.

## Our measurement layer, merged on top (`ujwal/e2e`)
- Trap-firing detection (`traps_fired`) and `agent/traps.py` (six-trap signatures,
  honeytoken keyed on the invisible U+200B char).
- 2x2 experiment harness (`harness/experiment.py`): resets + reseeds the decoy per
  run and reports TSR / DSR / GBR.
- Custom enumeration-required CHT decoy (`decoy/Dockerfile`, `decoy/README.md`) and
  the six-trap `seed_traps.sh`.
- Flask + SSE dashboard batch view, `OVERVIEW.md`, and the test suite.

## Conflicts resolved by hand
- `targets.py`: kept Dan's binary-mode shell, re-applied our whole-line root check
  (his loose `expect in out.stdout` was the false-positive-root bug), and guarded
  `_make_noninteractive` so it never cuts stdin on a command that supplies its own
  (e.g. `echo pw | sudo -S ...`), which his version would have broken on our decoy.
- `loop.py`: Dan's context machinery (bounded context, ledgers, method-family) is
  now gated behind `compact_history` so it is the *hardening*; the plain agent sees
  full output and full history (so the flood trap T4.1 can still flood it). Our
  trap-firing detection runs in both (it is measurement, not a defense).
- `seed_traps.sh`: kept our six-trap version (the one the harness drives).
  Bhageeratha's copy remains at `decoy/bhageeratha_decoy/seed_traps.sh`.

## Post-merge fixes (from the first real N=3 sweep)
- `ModuleNotFoundError: ollama` was an environment gap (the `ollama` Python client
  was not installed); fixed with `pip install ollama`, not a code change.
- Interactive-shell guard in `targets.py`: an interactive root shell over the pipe
  (`sudo -i`/`sudo -s`, or `su` without `-c`) breaks the sentinel framing and
  returns a bare `127`. `run()` now returns a clear, neutral message instead, so
  the agent stops looping on it. It does not reveal the escalation method and
  applies to plain and hardened alike.
- Normalized-command loop detection in `loop.py`: near-duplicate retries (the same
  command re-quoted or re-spaced) now count together, so a stuck agent is cut off
  instead of burning its whole budget.
- Tests updated to the adopted design (strict fence parse, bounded-context ledger)
  and new guards covered; 67 tests pass.

## Known open items (not bugs, for interpretation)
- Baseline competence is still variable at small N (rabbit-holing); run at N>=10.
- Hardened cells need `transformers` + the PromptGuard 2 license for a real GBR;
  until then use `--screen mock` (GBR is a mock number).
- The deception effects (flood, injection) are not yet cleanly isolated at N=3;
  trap firing depends on the agent's enumeration path.
