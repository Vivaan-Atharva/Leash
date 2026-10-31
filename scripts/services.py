"""Start/stop the four Python services as separate processes (separate trust domains)."""
import os
import subprocess
import sys
import time
from contextlib import contextmanager

import httpx

from shared.config import ROOT

SERVICES = [  # order matters: hub first so others can publish events
    ("hub", "hub.app:app", "HUB"),
    ("rail", "rail.app:app", "RAIL"),
    ("gateway", "gateway.app:app", "GATEWAY"),
    ("shops", "shops.app:app", "SHOPS"),
]


def _port(env, key, default):
    return int(env.get(f"LEASH_PORT_{key}", default))


def start_all(env: dict | None = None, quiet: bool = False) -> list[subprocess.Popen]:
    env = {**os.environ, **(env or {})}
    host = env.get("LEASH_BIND", "127.0.0.1")
    defaults = {"HUB": 8000, "GATEWAY": 8001, "RAIL": 8002, "SHOPS": 8003}
    procs = []
    for name, appref, key in SERVICES:
        port = _port(env, key, defaults[key])
        cmd = [sys.executable, "-m", "uvicorn", appref, "--host", host, "--port", str(port),
               "--log-level", "warning"]
        out = subprocess.DEVNULL if quiet else None
        procs.append(subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=out, stderr=out))
    for name, _, key in SERVICES:
        port = _port(env, key, defaults[key])
        wait_healthy(f"http://127.0.0.1:{port}/health", name)
    return procs


def wait_healthy(u: str, name: str, timeout: float = 15) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(u, timeout=0.5).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise RuntimeError(f"{name} did not become healthy at {u}")


def stop_all(procs) -> None:
    for p in procs:
        p.terminate()
    for p in procs:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()


@contextmanager
def running(env: dict | None = None, quiet: bool = True):
    procs = start_all(env, quiet)
    try:
        yield procs
    finally:
        stop_all(procs)
