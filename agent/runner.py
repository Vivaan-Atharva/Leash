"""Run one scenario as the agent, in LIVE (LLM), REPLAY (golden trace) or SCRIPTED mode.

  python -m agent.runner S1 --mode live [--promote]   # LLM run, saves traces/S1-<ts>.json
  python -m agent.runner S1 --mode replay             # replays traces/golden/S1.json
  python -m agent.runner S1 --mode auto               # live if Ollama is ready, else replay, else scripted

In every mode the payment request is built, signed and routed live; only the agent's
reasoning is replayed in REPLAY mode. The mode actually used is announced (badge).
"""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import httpx

from agent import llm
from agent.run_scenarios import evaluate, load, phone_revoke, run_one
from agent.scripted import ScriptedAgent
from agent.tools import Tools
from shared.config import traces_dir, url
from shared.timeutil import now_iso

def golden_path(sid: str) -> Path:
    return traces_dir() / "golden" / f"{sid}.json"


def hub_event(http: httpx.Client, type_: str, data: dict, lane: str = "system") -> None:  # noqa: D103
    try:
        http.post(f"{url('hub')}/events", json={"type": type_, "lane": lane, "data": data})
    except httpx.HTTPError:
        pass


def resolve_mode(sid: str, requested: str) -> str:
    if requested in ("live", "auto"):
        if llm.ollama_ready():
            return "live"
        requested = "replay"
    if requested == "replay" and golden_path(sid).exists():
        return "replay"
    return "scripted"


def ensure_revoked(http: httpx.Client) -> bool:
    """S5 needs Asha to have pulled the leash. If the seed mandate is active (signed by the
    demo phone key), the demo phone key revokes it; a phone-signed mandate must be revoked
    on the phone."""
    cur = http.get(f"{url('gateway')}/mandates/current").json()
    if cur["status"] == "REVOKED":
        return True
    from shared.keys import public_key
    if cur["mandate"]["user"]["phone_pubkey"] != public_key("phone"):
        return False
    phone_revoke(http, ScriptedAgent(http))
    return True


class Recorder:
    def __init__(self):
        self.t0 = time.perf_counter()
        self.steps: list[dict] = []

    def __call__(self, type_: str, data: dict) -> None:
        t = round(time.perf_counter() - self.t0, 3)
        if type_ == "agent.thought":
            self.steps.append({"t": t, "kind": "thought", "text": data["text"]})
        elif type_ == "agent.tool_call":
            self.steps.append({"t": t, "kind": "tool", "tool": data["tool"], "args": data["args"]})


def _post_steps(sc: dict, tools: Tools) -> None:
    for p in sc.get("llm", {}).get("post", []):
        if p == "replay_last" and tools.last_request:
            tools.think("(Attacker resends the exact same signed request.)")
            tools.send(tools.last_request)


ATTACK_TASK = "Reorder Asha's usual: 1 Amul milk and 1 Modern whole wheat bread from freshcart.in."
ATTACK_START = "freshcart.in/product/FC-MILK-AMUL-500"


def attack_scenario() -> dict:
    """A judge's own injection (planted by the hub). Only meaningful with a real model."""
    return {"id": "ATTACK", "name": "Judge's attack", "attack": True, "task": ATTACK_TASK,
            "llm": {"start_url": ATTACK_START}, "expected": None}


def run(sid: str, mode: str = "auto", promote: bool = False, speed: float = 1.0) -> dict:
    http = httpx.Client(timeout=15)
    sc = attack_scenario() if sid == "ATTACK" else load(sid)
    used = resolve_mode(sid, mode)
    reason = None
    if mode in ("live", "auto") and used != "live":
        reason = f"Ollama/{llm.model_name()} unavailable"
    elif mode == "replay" and used == "scripted":
        reason = f"no golden trace for {sid}"
    if sid == "ATTACK" and used != "live":
        hub_event(http, "director.moment", {"scenario": sid, "status": "error",
                                            "text": "The attack console needs the LIVE model (Ollama)."})
        return {"id": sid, "mode": used, "ok": False, "error": "needs_live_model"}
    hub_event(http, "system.mode", {"mode": used.upper(), "scenario": sid, "requested": mode.upper(),
                                    "fallback_reason": reason,
                                    "model": llm.model_name() if used == "live" else None})
    http.post(f"{url('hub')}/director/active", json={
        "scenario": sid, "name": sc["name"], "attack": sc["attack"], "mode": used})

    if sc.get("needs_revoke") and used != "scripted" and not ensure_revoked(http):
        hub_event(http, "director.moment", {"scenario": sid, "status": "waiting_for_revoke",
                                            "text": "Revoke on Asha's phone first."})
        return {"id": sid, "mode": used, "ok": False, "error": "waiting_for_revoke"}

    if sid != "ATTACK":  # the hub already planted the judge's injection
        http.post(f"{url('shops')}/admin/scenario/{sid}").raise_for_status()
    hub_event(http, "director.moment", {"scenario": sid, "name": sc["name"], "task": sc["task"],
                                        "status": "running", "mode": used.upper()})

    main_traces: list[dict] = []
    if used == "scripted":
        agent = ScriptedAgent(http)
        agent.set_task(sc["task"], sid)
        res = run_one(sc, agent, http, announce=False)
        main_traces = agent.tools["agent"].traces + agent.tools["rogue"].traces
    else:
        cfg = sc.get("llm", {})
        rec = Recorder()
        tools = Tools(http, cfg.get("signer", "agent"), on_event=rec, scenario=sid)
        if used == "replay":
            tools.set_task(sc["task"])
        if used == "live":
            meta = llm.run_llm(sc["task"], cfg["start_url"], tools,
                               stop_after_checkout=cfg.get("stop_after_checkout", True))
        else:
            meta = replay(golden_path(sid), tools, speed)
        _post_steps(sc, tools)
        main_traces = tools.traces
        res = evaluate(sc, tools.routes) if sc.get("expected") else _summary(sc, tools.routes)
        if used == "live":
            trace = {"scenario": sid, "model": meta["model"], "recorded_at": now_iso(),
                     "task": sc["task"], "start_url": cfg["start_url"], "steps": rec.steps,
                     "result": {k: res[k] for k in ("left_paid_paise", "right_paid_paise", "right", "ok")}}
            traces_dir().mkdir(parents=True, exist_ok=True)
            path = traces_dir() / f"{sid}-{time.strftime('%Y%m%d-%H%M%S')}.json"
            path.write_text(json.dumps(trace, indent=1, ensure_ascii=False))
            res["trace"] = str(path)
            if sc["id"] == "ATTACK":
                promote = False
            if promote and res["ok"]:
                golden_path(sid).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(path, golden_path(sid))
                res["promoted"] = True
    res["mode"] = used
    if main_traces and (sc.get("counterfactual_steps") or sid == "ATTACK"):
        cf_steps = counterfactual(http, sc, used, main_traces)
        if used == "live" and res.get("trace") and cf_steps is not None:
            p = Path(res["trace"])
            t = json.loads(p.read_text())
            t["counterfactual_steps"] = cf_steps
            p.write_text(json.dumps(t, indent=1, ensure_ascii=False))
            if res.get("promoted"):
                shutil.copy(p, golden_path(sid))
    hub_event(http, "director.moment", {"scenario": sid, "status": "done", "ok": res["ok"],
                                        "left_paid_paise": res["left_paid_paise"],
                                        "right_paid_paise": res["right_paid_paise"]})
    return res


def exec_steps(tools: Tools, steps: list[dict]) -> None:
    """Run scripted steps (visit / think / buy) through a Tools instance."""
    for st in steps:
        if st["do"] == "visit":
            tools.call("get_page", {"url": f"/{st['shop']}/product/{st['sku']}"})
        elif st["do"] == "think":
            tools.think(st["text"])
        elif st["do"] == "buy":
            for _ in range(st.get("times", 1)):
                for it in st["items"]:
                    tools.call("add_to_cart", {"shop": st["shop"], "sku": it["sku"], "qty": it["qty"]})
                tools.call("checkout", {"shop": st["shop"]})


def counterfactual(http: httpx.Client, sc: dict, used: str, main_traces: list[dict]) -> list[dict] | None:
    """Same agent, same task, honest page (no hidden text, honest prices), dry run: no money moves.
    Shows what the injection *caused*. Returns recorded steps in LIVE mode (saved into the trace)."""
    cfg = sc.get("llm", {})
    rec = Recorder()
    cf = Tools(http, cfg.get("signer", "agent"), on_event=rec, quiet=True, dry_run=True, scenario=sc["id"])
    hub_event(http, "attack.counterfactual", {"scenario": sc["id"], "status": "running"}, lane="both")
    http.post(f"{url('shops')}/admin/clean", json={"clean": True})
    try:
        if used == "live":
            llm.run_llm(sc["task"], cfg["start_url"], cf, stop_after_checkout=cfg.get("stop_after_checkout", True))
        elif used == "replay":
            steps = json.loads(golden_path(sc["id"]).read_text()).get("counterfactual_steps")
            if not steps:
                return None
            cf.set_task(sc["task"])
            for st in steps:
                cf.think(st["text"]) if st["kind"] == "thought" else cf.call(st["tool"], st["args"])
        else:
            cf.set_task(sc["task"])
            exec_steps(cf, sc.get("counterfactual_steps", []))
    except (httpx.HTTPError, KeyError, ValueError) as e:
        hub_event(http, "attack.counterfactual", {"scenario": sc["id"], "status": "error", "error": str(e)}, lane="both")
        return None
    finally:
        http.post(f"{url('shops')}/admin/clean", json={"clean": False})
    anchor = next((t for t in main_traces if t["culprit"] is not None), main_traces[-1])
    hub_event(http, "attack.counterfactual", {
        "scenario": sc["id"], "status": "done", "mode": used, "for_request_id": anchor["request_id"],
        "log": cf.log[-30:], "traces": cf.traces,
    }, lane="both")
    return rec.steps


def _summary(sc: dict, routes: list[dict]) -> dict:
    return {"id": sc["id"], "name": sc["name"], "attack": sc["attack"], "ok": True,
            "left_paid_paise": sum(r["left"]["amount_paise"] for r in routes),
            "right_paid_paise": sum(r["right"]["amount_paise"] for r in routes),
            "right": [{"outcome": r["right"].get("decision", {}).get("outcome")} for r in routes]}


def replay(path: Path, tools: Tools, speed: float = 1.0) -> dict:
    """Replay the recorded reasoning with its timing; re-run every tool call for real."""
    trace = json.loads(path.read_text())
    t0 = time.perf_counter()
    for step in trace["steps"]:
        wait = step["t"] / speed - (time.perf_counter() - t0)
        if wait > 0:
            time.sleep(min(wait, 8))
        if step["kind"] == "thought":
            tools.think(step["text"])
        else:
            tools.call(step["tool"], step["args"])
    return {"model": trace.get("model"), "replayed_from": path.name}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario")
    ap.add_argument("--mode", default="auto", choices=["auto", "live", "replay", "scripted"])
    ap.add_argument("--promote", action="store_true", help="save as golden trace if outcome matches")
    ap.add_argument("--speed", type=float, default=1.0)
    a = ap.parse_args(argv)
    res = run(a.scenario.upper(), a.mode, a.promote, a.speed)
    print(json.dumps({k: v for k, v in res.items() if k != "right"}, ensure_ascii=False))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
