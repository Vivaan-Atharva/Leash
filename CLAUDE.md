You are building Leash. Read LEASH_BUILD_SPEC.md before every phase.
- Work only on the current phase. Plan first, then implement, then run the phase's acceptance tests.
- Never put an LLM call inside gateway/, rail/ or shared/.
- All money is integer paise. Never floats.
- Every signed object uses canonical JSON (sorted keys, no whitespace, UTF-8).
- Every gateway decision must be reproducible: same input + same state = same decision.
- Keep the demo path working at all times. Run `make demo-check` before saying a task is done.
- UI comes from Stitch exports in design/. Match them closely; don't invent a new visual style.
- Prefer simple code that is obviously correct over clever code.

## Repo notes
- Python venv: `.venv/` (`make setup`). Keys live in `keys/` (gitignored, `make keys`).
- Services: hub :8000, gateway :8001, rail :8002, shops :8003. `make dev` starts all four.
- Per-service SQLite files live in `data/` (gitignored). `LEASH_DATA_DIR` / `LEASH_KEYS_DIR` / `LEASH_PORT_*` override.
