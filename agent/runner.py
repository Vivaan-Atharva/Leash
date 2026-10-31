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


def hub_event(http: httpx.Client, type_: str, data: dict, lane: str = "system") -> None:
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


def run(sid: str, mode: str = "auto", promote: bool = False, speed: float = 1.0) -> dict:
    http = httpx.Client(timeout=15)
    sc = load(sid)
    used = resolve_mode(sid, mode)
    hub_event(http, "system.mode", {"mode": used.upper(), "scenario": sid,
                                    "model": llm.model_name() if used == "live" else None})
    http.post(f"{url('hub')}/director/active", json={
        "scenario": sid, "name": sc["name"], "attack": sc["attack"], "mode": used})

    if sc.get("needs_revoke") and used != "scripted" and not ensure_revoked(http):
        hub_event(http, "director.moment", {"scenario": sid, "status": "waiting_for_revoke",
                                            "text": "Revoke on Asha's phone first."})
        return {"id": sid, "mode": used, "ok": False, "error": "waiting_for_revoke"}

    http.post(f"{url('shops')}/admin/scenario/{sid}").raise_for_status()
    hub_event(http, "director.moment", {"scenario": sid, "name": sc["name"], "task": sc["task"],
                                        "status": "running", "mode": used.upper()})

    if used == "scripted":
        agent = ScriptedAgent(http)
        res = run_one(sc, agent, http, announce=False)
    else:
        cfg = sc.get("llm", {})
        rec = Recorder()
        tools = Tools(http, cfg.get("signer", "agent"), on_event=rec)
        if used == "live":
            meta = llm.run_llm(sc["task"], cfg["start_url"], tools,
                               stop_after_checkout=cfg.get("stop_after_checkout", True))
        else:
            meta = replay(golden_path(sid), tools, speed)
        _post_steps(sc, tools)
        res = evaluate(sc, tools.routes)
        if used == "live":
            trace = {"scenario": sid, "model": meta["model"], "recorded_at": now_iso(),
                     "task": sc["task"], "start_url": cfg["start_url"], "steps": rec.steps,
                     "result": {k: res[k] for k in ("left_paid_paise", "right_paid_paise", "right", "ok")}}
            traces_dir().mkdir(parents=True, exist_ok=True)
            path = traces_dir() / f"{sid}-{time.strftime('%Y%m%d-%H%M%S')}.json"
            path.write_text(json.dumps(trace, indent=1, ensure_ascii=False))
            res["trace"] = str(path)
            if promote and res["ok"]:
                golden_path(sid).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(path, golden_path(sid))
                res["promoted"] = True
    res["mode"] = used
    hub_event(http, "director.moment", {"scenario": sid, "status": "done", "ok": res["ok"],
                                        "left_paid_paise": res["left_paid_paise"],
                                        "right_paid_paise": res["right_paid_paise"]})
    return res


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
