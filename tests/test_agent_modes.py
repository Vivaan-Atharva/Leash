"""LIVE (against a fake Ollama), trace recording, golden promotion and REPLAY, end to end."""
import json
import os
import subprocess
import sys
import tempfile

import httpx
import pytest

from scripts.services import running, wait_healthy
from shared.config import ROOT, url

FAKE_PORT = 18011


@pytest.fixture(scope="module")
def stack():
    traces = tempfile.mkdtemp(prefix="leash-traces-")
    os.environ["LEASH_TRACES_DIR"] = traces
    os.environ["OLLAMA_URL"] = f"http://127.0.0.1:{FAKE_PORT}"
    fake = subprocess.Popen([sys.executable, "-m", "uvicorn", "tests.fake_ollama:app", "--port",
                             str(FAKE_PORT), "--log-level", "warning"], cwd=ROOT)
    try:
        wait_healthy(f"http://127.0.0.1:{FAKE_PORT}/api/tags", "fake ollama")
        with running():
            yield traces
    finally:
        fake.terminate()
        os.environ.pop("LEASH_TRACES_DIR")
        os.environ.pop("OLLAMA_URL")


def test_live_run_records_and_promotes_then_replays(stack):
    from agent import runner
    httpx.post(f"{url('hub')}/demo/reset").raise_for_status()
    live = runner.run("S1", "live", promote=True)
    assert live["mode"] == "live" and live["ok"], live
    assert live["left_paid_paise"] == 396000 and live["right_paid_paise"] == 0
    golden = json.loads(open(os.path.join(stack, "golden", "S1.json")).read())
    assert [s["tool"] for s in golden["steps"] if s["kind"] == "tool"] == ["get_page", "add_to_cart", "checkout"]

    httpx.post(f"{url('hub')}/demo/reset").raise_for_status()
    rep = runner.run("S1", "replay", speed=50)
    assert rep["mode"] == "replay" and rep["ok"], rep
    # replay went through the live gateway: a fresh decision is in the log
    assert httpx.get(f"{url('gateway')}/log/verify").json()["length"] >= 3


def test_replay_without_golden_falls_back_to_scripted(stack):
    from agent import runner
    httpx.post(f"{url('hub')}/demo/reset").raise_for_status()
    res = runner.run("S3", "replay")
    assert res["mode"] == "scripted" and res["ok"]


def test_s5_revokes_seed_mandate_then_blocks(stack):
    from agent import runner
    httpx.post(f"{url('hub')}/demo/reset").raise_for_status()
    res = runner.run("S5", "live")
    # the fake model only buys the milk on the page, so check the block, not the ₹ total
    assert res["right"][0]["failing"] == [6] and res["right_paid_paise"] == 0
    assert res["left_paid_paise"] > 0


def test_score_counts_attack_losses(stack):
    from agent import runner
    httpx.post(f"{url('hub')}/demo/reset").raise_for_status()
    runner.run("S0", "scripted")
    runner.run("S3", "scripted")
    s = httpx.get(f"{url('hub')}/score").json()
    assert s["left_lost_paise"] == 13500 and s["right_lost_paise"] == 0
    assert s["left_paid_paise"] == 9600 + 13500
