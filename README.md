# Leash

A payment gateway between an AI shopping agent and a UPI Reserve Pay–style rail. The user signs a
mandate on their phone; every payment the agent asks for must pass six deterministic checks, or ₹0 moves.
The agent has no key that moves money on the protected wallet. Only the gateway does.

## Run
```
make setup          # venv, Python deps, demo keys, web deps
make dev            # hub :8000, gateway :8001, rail :8002, shops :8003 (+ seed)
make web            # Next.js on :3000 → http://localhost:3000/control
make scenario S=all # scripted agent runs S0–S9 through both lanes
make test           # unit + end-to-end tests
make demo-check     # preflight
```

## Layout
`shared/` contracts, canonical JSON, signing · `gateway/` six checks + hash-chained log ·
`rail/` mock Reserve Pay · `hub/` events, mirror router, reset · `shops/` three shops with hidden
injections · `agent/` scripted agent (LLM agent in Phase 2) · `eval/scenarios/` S0–S9 · `web/` UI.

See `LEASH_BUILD_SPEC.md` for the full plan.
