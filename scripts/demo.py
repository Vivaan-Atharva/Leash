"""`make demo`: start every service, a production web build, reset to seed, open Mission Control.

Ctrl-C stops everything. Phones on the same network open the URL shown in the QR code.
"""
import os
import signal
import subprocess
import sys
import time
import webbrowser

import httpx

from scripts.services import start_all, stop_all, wait_healthy
from shared.config import ROOT, url
from shared.keys import ensure_keys

WEB = ROOT / "web"


def main() -> None:
    ensure_keys()
    os.environ.setdefault("LEASH_BIND", "0.0.0.0")
    procs = start_all()
    if not (WEB / ".next" / "BUILD_ID").exists():
        print("Building the web app (first run only)…")
        subprocess.run(["npm", "run", "build"], cwd=WEB, check=True)
    web = subprocess.Popen(["npx", "next", "start", "-H", "0.0.0.0", "-p", os.environ.get("LEASH_WEB_PORT", "3000")],
                           cwd=WEB, stdout=subprocess.DEVNULL)
    procs.append(web)
    wait_healthy("http://127.0.0.1:3000/control", "web", timeout=60)
    httpx.post(f"{url('hub')}/demo/reset", timeout=10).raise_for_status()
    phone = httpx.get(f"{url('hub')}/netinfo").json()["phone_url"]
    print(f"\nLeash is up.\n  Mission Control  http://localhost:3000/control   (press F for fullscreen)\n"
          f"  Asha's phone     {phone}   (or scan the QR on Mission Control)\n"
          "Keys: → next · ← back · 0–9 scenario · X x-ray · T tamper · L live/replay · R reset\n")
    webbrowser.open("http://localhost:3000/control")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        stop_all(procs)


if __name__ == "__main__":
    main()
