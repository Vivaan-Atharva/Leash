"""Aggregate results.csv for the results screen and the chart."""
import csv
from collections import defaultdict
from pathlib import Path

from eval.harness import DEFENCES, RESULTS, load_cases


def summarise(path: Path = RESULTS) -> dict:
    if not path.exists():
        return {"available": False}
    rows = list(csv.DictReader(path.open()))
    if not rows:
        return {"available": False}
    cells: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        cells[(r["case_id"], r["defence"])].append(r)
    present = [d for d, _, _ in DEFENCES if any(k[1] == d for k in cells)]
    cases = [c for c in load_cases() if any(k[0] == c["id"] for k in cells)]
    matrix, lost, honest_ok = [], {d: 0 for d in present}, {d: 0 for d in present}
    for c in cases:
        row = {"case_id": c["id"], "name": c["name"], "kind": c["kind"], "in_scope": bool(c.get("in_scope")),
               "technique": c.get("technique", ""), "cells": {}}
        for d in present:
            rs = cells.get((c["id"], d), [])
            if not rs:
                continue
            mean_lost = round(sum(int(r["lost_paise"]) for r in rs) / len(rs))
            ok_runs = sum(int(r["honest_ok"]) for r in rs)
            row["cells"][d] = {"runs": len(rs), "mean_lost_paise": mean_lost,
                               "lost_runs": sum(int(r["lost_paise"]) > 0 for r in rs),
                               "honest_ok_runs": ok_runs,
                               "outcomes": [r["outcomes"] for r in rs], "failing": [r["failing"] for r in rs]}
            if c["kind"] == "attack":
                lost[d] += mean_lost
            elif ok_runs == len(rs):
                honest_ok[d] += 1
        matrix.append(row)
    return {
        "available": True,
        "mode": rows[0]["mode"], "model": rows[0]["model"], "runs": max(int(r["run"]) for r in rows),
        "generated_at": max(r["at"] for r in rows),
        "defences": present,
        "lost_paise": lost,
        "honest_total": sum(1 for c in cases if c["kind"] == "honest"),
        "honest_allowed": honest_ok,
        "attack_total": sum(1 for c in cases if c["kind"] == "attack"),
        "matrix": matrix,
    }
