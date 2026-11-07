# Tasks and timeline: AgentTrap

See PRD.md for each stage's purpose and CLAUDE.md for constraints. Four people, work split evenly. Ujwal runs and executes most of the code, but the build is shared so no one is overloaded.

## Build phase (stages 1 to 4: environment, baseline agent, traps, hardening)

| Owner | Tasks |
|---|---|
| Ujwal | Attacker agent loop on Ollama; hardened-agent config; Flask dashboard UI (with Ivan's input); integration |
| Bhageerath | Shell-on-host decoy (with Dan); the Trap techniques, including the symlink loop he proposed |
| Dan | Run harness (N runs, logging TSR, DSR, tokens, time); shell-on-host decoy (with Bhageerath); Cloak and Honey techniques |
| Ivan | Research: pull CHT and PromptGuard, threat model and framework mapping; dashboard content and insights for Ujwal |

## Delivery phase (stages 5 to 7: experiment, demo and write-up, submit)

| Owner | Tasks |
|---|---|
| Ujwal | Freeze core; dashboard polish; script the live demo; stronger-attacker honesty check |
| Bhageerath | Trap and decoy polish; help run the 2x2 sweeps; help record the backup video |
| Dan | Run all four 2x2 cells; final metrics and clean charts; record backup video |
| Ivan | Slides and report; the result slides (2x2 and PromptGuard-vs-techniques) |

The report is split four ways.

## Timeline

| When | What |
|---|---|
| Week 1 (20 to 26 Oct) | Stages 1 to 2: environment, baseline agent rooting the clean host |
| Week 2 (24 to 30 Oct) | Stages 3 to 4: five traps seeded, hardening added |
| By Sun 2 Nov | Stage 5: full 2x2 run, results table filled. Hard freeze: all build work stops here. |
| 3 to 9 Nov | Light buffer only (exam week). Nothing critical lands here. |
| Around 10 Nov | Stages 6 to 7: demo, slides, report, submit. Presentation is course Week 13. |

Phases overlap on purpose: traps start while the baseline agent is being finished, and the experiment starts before every trap is perfect, so a slow trap does not block measurement. If anything runs late, the freeze date holds and scope drops (fewer extra traps, not fewer 2x2 cells).

## Coordination

- The decoy host is shared by Bhageerath and Dan, so no single person carries it.
- Ujwal owns integration (keeping the parts fitting together) and builds the dashboard UI with Ivan's input.
- Ivan stays off the critical path (research and content), so his internship schedule cannot block the build.
