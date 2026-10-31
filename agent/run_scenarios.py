"""Run scenarios with the scripted agent and print the §5 table.

  python -m agent.run_scenarios all      # S0–S5 as one continuous stage run, then S6–S9 each from fresh
  python -m agent.run_scenarios S1 S3    # each from a fresh reset
"""
import json
import sys
from pathlib import Path

import httpx

from agent.scripted import ScriptedAgent
from shared.config import url
from shared.crypto import sign_obj
from shared.keys import signing_key
from shared.money import inr
from shared.timeutil import now_iso

SCEN_DIR = Path(__file__).resolve().parent.parent / "eval" / "scenarios"
ALL = [f"S{i}" for i in range(10)]
STAGE = ALL[:6]


def load(sid: str) -> dict:
    return json.loads((SCEN_DIR / f"{sid}.json").read_text())


def reset(http: httpx.Client) -> None:
    r = http.post(f"{url('hub')}/demo/reset")
    r.raise_for_status()
    if not r.json()["ok"]:
        raise RuntimeError(f"reset failed: {r.json()}")


def phone_revoke(http: httpx.Client, agent: ScriptedAgent) -> dict:
    """What Asha's phone does: sign a revoke for the current mandate."""
    mid = agent.mandate_id()
    body = sign_obj({"mandate_id": mid, "action": "revoke", "ts": now_iso()}, signing_key("phone"))
    right = http.post(f"{url('gateway')}/mandates/{mid}/revoke", json=body).json()
    left = http.post(f"{url('rail')}/blocks/blk_l_01/revoke", json={}).json()  # Reserve Pay today
    return {"right": right, "left": left}


def run_one(sc: dict, agent: ScriptedAgent, http: httpx.Client, announce: bool = True) -> dict:
    if announce:
        http.post(f"{url('shops')}/admin/scenario/{sc['id']}").raise_for_status()
        http.post(f"{url('hub')}/director/active", json={
            "scenario": sc["id"], "name": sc["name"], "attack": sc["attack"], "mode": "scripted"})
        agent.emit("director.moment", {"scenario": sc["id"], "name": sc["name"], "task": sc.get("task")})
    routes = []
    for step in sc["steps"]:
        do = step["do"]
        if do == "visit":
            agent.get_page(step["shop"], step["sku"])
        elif do == "think":
            agent.think(step["text"])
        elif do == "buy":
            for _ in range(step.get("times", 1)):
                for it in step["items"]:
                    agent.add_to_cart(step["shop"], it["sku"], it["qty"])
                routes.append(agent.checkout(step["shop"], step.get("signer", "agent")))
        elif do == "replay_last":
            routes.append(agent.send(agent.last_request))
        elif do == "revoke":
            phone_revoke(http, agent)
        else:
            raise ValueError(f"unknown step {do}")
    return evaluate(sc, routes)


def evaluate(sc: dict, routes: list[dict]) -> dict:
    """Compare what both lanes did against the scenario's expected outcome."""
    decisions = [r["right"].get("decision", {}) for r in routes]
    right = [{"outcome": d.get("outcome", "ERROR"),
              "failing": [c["n"] for c in d.get("checks", []) if not c["pass"]],
              "decided_in_us": d.get("decided_in_us"),
              "decision_id": d.get("decision_id")} for d in decisions]
    result = {
        "id": sc["id"], "name": sc["name"], "attack": sc["attack"],
        "left_paid_paise": sum(r["left"]["amount_paise"] for r in routes),
        "right_paid_paise": sum(r["right"]["amount_paise"] for r in routes),
        "right": right,
    }
    exp = sc["expected"]
    result["ok"] = (result["left_paid_paise"] == exp["left_paid_paise"]
                    and result["right_paid_paise"] == exp["right_paid_paise"]
                    and [{"outcome": r["outcome"], "failing": r["failing"]} for r in right] == exp["right"])
    return result


def run(ids: list[str]) -> list[dict]:
    http = httpx.Client(timeout=10)
    agent = ScriptedAgent(http)
    results = []
    if ids == ALL:
        reset(http)
        for sid in STAGE:  # the stage demo: one continuous week for Asha
            results.append(run_one(load(sid), agent, http))
        ids = ALL[6:]
    for sid in ids:
        reset(http)
        results.append(run_one(load(sid), agent, http))
    return results


def _outcomes(right: list[dict]) -> str:
    if len(right) == 1:
        return right[0]["outcome"]
    a = sum(r["outcome"] == "ALLOWED" for r in right)
    return f"{a}× ALLOWED, {len(right) - a}× BLOCKED"


def print_table(results: list[dict]) -> None:
    hdr = f"{'ID':<4}{'Scenario':<20}{'Left (no Leash)':>16}  {'Right (Leash)':<26}{'Right paid':>11}  {'Failing':<10}{'μs':>6}  OK"
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        failing = sorted({n for x in r["right"] for n in x["failing"]})
        us = max((x["decided_in_us"] or 0) for x in r["right"]) if r["right"] else 0
        print(f"{r['id']:<4}{r['name']:<20}{inr(r['left_paid_paise']) + ' paid':>16}  "
              f"{_outcomes(r['right']):<26}{inr(r['right_paid_paise']):>11}  "
              f"{','.join(map(str, failing)) or '–':<10}{us:>6}  {'✓' if r['ok'] else '✕'}")
    stage = [r for r in results if r["id"] in STAGE and r["attack"]]
    if stage:
        print("-" * len(hdr))
        left = sum(r["left_paid_paise"] for r in stage)
        right = sum(r["right_paid_paise"] for r in stage)
        print(f"Stage demo S0–S5 · lost to attacks: left {inr(left)} · right {inr(right)}")


def main(argv: list[str]) -> int:
    args = [a.upper() for a in argv] or ["ALL"]
    ids = ALL if args == ["ALL"] else args
    results = run(ids)
    print_table(results)
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
