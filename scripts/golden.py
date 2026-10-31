"""`make golden`: record S0–S5 with the real model and promote the runs that behave as intended.

For each scenario it tries a few seeds (seed 7 = deterministic, others add a little temperature).
A run is promoted to traces/golden/<S>.json only if it matches the scenario's expected outcome exactly
(same ₹ on both lanes, same decisions and failing checks). With --loose it will also accept a run whose
gateway decisions match but whose amounts differ (the stage totals then won't be exactly ₹4,431).

Needs the services running (`make dev`) and Ollama with the model pulled.
"""
import argparse
import os
import shutil
import sys
import time

import httpx

from agent import llm, runner
from agent.run_scenarios import load
from shared.config import url
from shared.money import inr

SEEDS = [7, 11, 23]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("scenarios", nargs="*", default=["S0", "S1", "S2", "S3", "S4", "S5"])
    ap.add_argument("--loose", action="store_true")
    ap.add_argument("--tries", type=int, default=len(SEEDS))
    a = ap.parse_args(argv)
    try:
        httpx.get(f"{url('hub')}/health", timeout=2).raise_for_status()
    except httpx.HTTPError:
        print("Services aren't running. Start them with `make dev` in another terminal.")
        return 2
    if not llm.ollama_ready():
        print(f"Ollama or {llm.model_name()} isn't ready. Run `ollama serve` and `ollama pull {llm.model_name()}`.")
        return 2
    print(f"Recording golden traces with {llm.model_name()} …\n")
    rows, failed = [], 0
    for sid in [s.upper() for s in a.scenarios]:
        exp = load(sid)["expected"]
        best, status = None, "✕ no matching run"
        for seed in SEEDS[: a.tries]:
            os.environ["LEASH_SEED"] = str(seed)
            httpx.post(f"{url('hub')}/demo/reset", timeout=10).raise_for_status()
            t0 = time.time()
            res = runner.run(sid, "live", promote=True)
            secs = time.time() - t0
            if res.get("mode") != "live":
                status = f"✕ ran {res.get('mode')}, not live"
                break
            got = [(r["outcome"], r["failing"]) for r in res["right"]]
            want = [(r["outcome"], r["failing"]) for r in exp["right"]]
            res["secs"], res["seed"] = secs, seed
            if res.get("promoted"):
                best, status = res, "✓ exact"
                break
            if got == want and best is None:
                best, status = res, "~ decisions match, amounts differ"
        if best and status.startswith("~") and a.loose:
            shutil.copy(best["trace"], runner.golden_path(sid))
            status += " (promoted, --loose)"
        if not status.startswith("✓") and "promoted" not in status:
            failed += 1
        rows.append((sid, status, best))
    httpx.post(f"{url('hub')}/demo/reset", timeout=10)
    os.environ.pop("LEASH_SEED", None)

    print(f"{'':4}{'result':<44}{'left':>9}{'right':>8}  {'seed':>4}  {'time':>6}")
    for sid, status, r in rows:
        if r:
            print(f"{sid:<4}{status:<44}{inr(r['left_paid_paise']):>9}{inr(r['right_paid_paise']):>8}  {r['seed']:>4}  {r['secs']:>5.0f}s")
        else:
            print(f"{sid:<4}{status}")
    print("\nPromoted traces are in traces/golden/. Commit them: git add traces/golden && git commit -m 'Golden traces'")
    if failed:
        print(f"{failed} scenario(s) didn't behave as intended. Send the newest traces/<S>-*.json for tuning,\n"
              "or rerun with `make golden LOOSE=1` to accept runs whose gateway decisions match.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
