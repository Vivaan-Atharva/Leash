# Leash threat model

## What we protect
1. **Asha's money**: the reserve block on her account.
2. **Asha's intent**: only what she signed for should be bought: these shops, these items, these limits.
3. **The evidence**: after the fact, anyone can check what was asked for, what was decided, and why.

## Who we trust
| Component | Trust | Holds |
|---|---|---|
| Asha's phone | trusted | phone key: signs the mandate, revokes, approves step-ups |
| Gateway | trusted, deterministic, **no LLM** | gateway key: the only key that can debit the protected wallet |
| Rail | trusted | refuses any debit on the protected block without a valid gateway signature |
| Agent + LLM | **untrusted**: can be manipulated by what it reads | agent key: signs requests, moves no money on its own |
| Shops | **untrusted** | set their own pages and prices |

The central design point: the agent's key is not a payment key. Even a fully compromised agent can only
*ask*, and every ask goes through the six checks.

## Attacker
Controls shop content (hidden prompt injections in text, comments, alt text, JSON-LD, fake banners),
can run look-alike shops (`fresh-kart.in`), can set any price, can capture and replay signed requests,
and can sign with a key of their own. They do **not** control the phone, the gateway host or the rail.

## Attacks and what stops them
| Attack | Scenario | Stopped by |
|---|---|---|
| Hidden "bulk order pre-approved" | S1, A01, A10, A11 | 3 limits, 4 intent |
| Look-alike shop | S2, A02, A09 | 2 merchant (exact match) |
| Inflated price | S3, A03, A08 | 5 price (gateway's own reference catalogue) |
| Gift card / off-list item | S4, A04, A06, A07 | 2 category, 4 intent |
| Payment after revoke | S5 | 6 validity (and the rail block is closed) |
| Order splitting | S6, A05 | 3 weekly cap (only partly: see limits) |
| Replay | S7 | 6 nonce |
| Unregistered agent key | S8 | 1 identity |
| Agent bypasses the gateway | test | rail requires the gateway signature |
| Edited log row | tamper demo | hash chain verification |

## Limits (in scope by design)
- **In-scope steering:** a manipulated choice that's inside the mandate (allowed brand, fair price,
  allowed shop) passes the checks. Step-up asks Asha when it's a new brand or a large order.
- **Order splitting and duplicates** under the weekly cap pass: each order is individually valid.
- **Reference catalogue correctness:** check 5 is only as good as the gateway's reference prices.
- **Whole-chain rewrite:** the hash chain detects edits, but someone with write access to the gateway's
  database could rebuild the whole chain. Fix: periodically sign and publish the chain head (not built).
- **Demo shortcuts:** keys are files in `keys/`, the phone key lives in browser `localStorage`, services
  talk over plain HTTP on a local network, and the shop sites and rail are mocks.

## Why no LLM in the money path
Same input plus same state gives the same decision, every time. A judge can write any injection in the
attack console: it can change what the agent *wants*, but not what the gateway *allows*.
