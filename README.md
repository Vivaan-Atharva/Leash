# Leash

**A payment gateway that keeps AI shopping agents on a leash.** The user signs a mandate on their phone
(what the agent may buy, where, and for how much). Every payment the agent asks for must pass six
deterministic checks, or ₹0 moves. Every decision is written to a hash-chained log that produces a
signed dispute report with a liability verdict.

> The agent doesn't have a key that moves money. Only the gateway does.

Built by team ByteMe at Kodikon 6.0.

## The demo: one brain, two wallets
One AI agent shops on untrusted pages, some of them carrying hidden prompt injections. Each payment
request it signs is **mirrored** to two wallets:

- **Left (no Leash):** the request goes straight to the rail. This is how agent payments work today.
- **Right (with Leash):** the request has to pass the gateway. The wallet only accepts debits co-signed by the gateway's key.

Over the stage scenarios S0–S5, the left wallet loses **₹4,431** and the right loses **₹0**.

## Architecture
```
 Phone (/phone) ──signs mandate, revokes, approves──▶ gateway :8001 ◀── six checks, no LLM
                                                        │  hash-chained audit log, signed decisions
 agent (Ollama LLM) ──tool calls──▶ shops :8003         │ gateway-signed debit
        │ (untrusted pages, hidden injections)          ▼
        └── signed PaymentRequest ──▶ hub :8000 ──mirror──▶ rail :8002 (mock UPI Reserve Pay)
                                       │  events (WebSocket)    wallet L: any agent-signed debit
                                       ▼                        wallet R: gateway-signed debits only
                         web :3000 (Mission Control, phone, report, results, attack console)
```
Each service is its own process with its own SQLite file and its own key (separate trust domains).

## The six checks (`gateway/checks.py`, pure functions)
| # | Check | Blocks |
|---|---|---|
| 1 | identity | requests not signed by the mandate's registered agent key |
| 2 | merchant | any shop not in the mandate (exact match; look-alikes are named), disallowed categories |
| 3 | limits | per-order, per-week and reserve-block limits, using the gateway's own reference prices |
| 4 | intent | items, quantities and brands that aren't on Asha's list |
| 5 | price | prices more than ±15% over the gateway's reference catalogue |
| 6 | validity | expired or revoked mandates, replayed nonces, stale requests |

After all six pass, **step-up** can hold an order (new brand, or over 70% of the per-order cap) until Asha
approves it on her phone. Decisions take about 2 ms.

## Beyond the checks: what makes this more than if-statements
| Layer | What it does | Grounded in |
|---|---|---|
| **Gateway as reference monitor** | The agent's key moves no money. Every payment is mediated, the decision code is small, pure and deterministic, and the rail only honours gateway-signed debits. | Anderson's reference monitor; capability-based security |
| **Provenance ledger → attack trace** | The agent runtime labels everything the model reads (TRUSTED task vs UNTRUSTED page text, and *how* text was hidden). Each payment field is traced to its source, so Mission Control shows the whole chain: hidden text → context → reasoning → tool call → signed request → both lanes. | CaMeL (Google DeepMind, 2025), FIDES (Microsoft Research, 2025) |
| **Counterfactual replay** | The same agent re-runs the same task on the clean page, as a dry run through `POST /evaluate` (no log entry, no money moved). It proves what the injection *caused*: "the hidden text turned ×1 into ×40". | Causal attribution by intervention |
| **Proven worst case** | The mandate and each defence become linear integer constraints over a fully hijacked agent. Z3 maximises total loss, money to the wrong shop, money on off-list items, and overpayment, and returns the optimal attack as a witness. A differential test checks the model against the real Python checks on 250 random requests. | Z3 SMT solver; formal verification |
| **Transparency log** | Every log entry is also a Merkle leaf; the gateway signs a tree head after each append. Reports carry an inclusion proof the browser verifies itself (SHA-256 + Ed25519). | Certificate Transparency, RFC 6962 / 9162 |

For Asha's mandate, Z3 proves: without Leash a hijacked agent can take **₹5,000**; under today's rails **₹500/week,
all of which can go to the wrong shop, on off-list items, or as pure overpayment**; under Leash **₹500/week, ₹0 to the
wrong shop, ₹0 off-list, at most ₹59.40 above fair price**.

The trace is attribution, not enforcement: it runs in the agent runtime, which the threat model treats as untrusted
(FIDES labels have been shown to be forgeable). The six checks decide; the trace explains.

## Run it
Needs Python 3.11+, Node 20+, and [Ollama](https://ollama.com) for LIVE mode.
```
git clone https://github.com/Vivaan-Atharva/Leash.git && cd Leash
make setup                 # venv, deps, this machine's demo keys, web deps
ollama pull qwen2.5:3b     # any tool-calling model; MODEL=llama3.1:8b to switch
make test                  # unit + end-to-end tests
make demo                  # starts everything, opens Mission Control
make golden                # once: record LIVE runs of S0–S5 as REPLAY backups, then commit traces/golden
```

| Page | What it's for |
|---|---|
| `/control` | Mission Control on the projector. `/control?table=1` is the 60-second table demo |
| `/phone` | Asha's phone: sign the mandate, live feed, slide-to-revoke, step-up approvals (scan the QR) |
| `/report/<decision_id>` | Dispute report with verdict and chain verification (printable) |
| `/attack` | "Try to trick it": write your own hidden instruction |
| `/results` | Attack-suite results: ₹ lost per defence |
| `/preflight` | Is everything ready? |

**Director keys (Mission Control):** `→`/`Space` next moment · `←` back · `0`–`9` jump to scenario ·
`X` X-ray · `A` attack trace · `P` proven worst case · `T` tamper/restore · `L` LIVE↔REPLAY · `R` reset ·
`F` fullscreen · click a stamp for its report.

**Modes:** LIVE runs the LLM. REPLAY replays a golden trace's reasoning, but every tool call and payment
is re-run live through the gateway and rail. SCRIPTED (no LLM, no golden trace) is the last-resort
fallback. The badge always shows which mode actually ran, and why it fell back.

## Other commands
```
make dev                 # just the services (hub, gateway, rail, shops) + seed
make web                 # Next.js dev server
make scenario S=all      # scripted agent runs S0–S9 and prints the table
make eval                # attack suite → eval/results.csv (LIVE if Ollama is up, else SCRIPTED)
make chart               # eval/chart.png
make record S=S1 PROMOTE=1
make demo-check          # preflight from the terminal
```

## Measured, not claimed
`eval/` holds 12 attacks and 8 honest purchases, each run 3 times under four defences: agent alone,
a hardened prompt, today's rails, and Leash. See [eval/README.md](eval/README.md). The committed results
are SCRIPTED; re-run `make eval` with Ollama for the LIVE numbers, including the hardened-prompt column.

## Limits, stated openly
Leash enforces the mandate. It can't tell a manipulated choice from a real one if both are inside the mandate:
- **In-scope steering:** an allowed brand at a fair price (S9). Step-up asks Asha first when it's a new brand.
- **Order splitting under the weekly cap,** and **duplicate orders** that both fit the limits (A05, A12).

See [docs/threat-model.md](docs/threat-model.md). For everything in one place (architecture, research, evidence, runbook, demo script), read [docs/HANDOFF.md](docs/HANDOFF.md).

## Repo
`shared/` contracts, canonical JSON, signing, paise · `gateway/` checks, step-up, audit log, report ·
`rail/` mock Reserve Pay · `hub/` events, mirror router, director, eval and attack endpoints ·
`shops/` three shops with switchable injections · `agent/` tools, Ollama agent, scripted agent, runner ·
`eval/` scenarios, attack suite, harness · `web/` Next.js UI · `traces/` recorded agent runs.
`LEASH_BUILD_SPEC.md` is the build plan.
