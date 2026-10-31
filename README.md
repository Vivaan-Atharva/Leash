# Leash

A payment gateway between an AI shopping agent and a UPI Reserve Pay–style rail. The user signs a
mandate on their phone; every payment the agent asks for must pass six deterministic checks, or ₹0 moves.
The agent has no key that moves money on the protected wallet. Only the gateway does.

## Run
```
make setup          # venv, Python deps, demo keys, web deps
make demo           # everything + production web build, opens Mission Control
make dev            # just the services: hub :8000, gateway :8001, rail :8002, shops :8003 (+ seed)
make web            # Next.js dev server on :3000 → /control (projector), /phone (Asha)
make scenario S=all # scripted agent runs S0–S9 through both lanes
make test           # unit + end-to-end tests
make demo-check     # preflight
make record S=S1 PROMOTE=1   # LIVE LLM run (Ollama); saves a golden REPLAY trace if it behaves as intended
make golden                  # record + promote S0–S5
```

## Director keys (Mission Control)
`→`/`Space` next moment · `←` back · `0`–`9` jump to scenario · `X` X-ray · `T` tamper/restore ·
`L` LIVE↔REPLAY · `R` reset · `F` fullscreen.

Modes: **LIVE** runs the LLM via Ollama. **REPLAY** replays a golden trace's reasoning, but every
tool call and payment is re-run live through the gateway and rail. **SCRIPTED** (no LLM, no golden trace)
is the last-resort fallback. The badge always shows which one ran.

## Layout
`shared/` contracts, canonical JSON, signing · `gateway/` six checks + hash-chained log ·
`rail/` mock Reserve Pay · `hub/` events, mirror router, reset · `shops/` three shops with hidden
injections · `agent/` tools, Ollama LLM agent, scripted agent, runner + traces · `eval/scenarios/` S0–S9 · `web/` UI.

See `LEASH_BUILD_SPEC.md` for the full plan.
