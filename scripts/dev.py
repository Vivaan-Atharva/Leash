"""`make dev`: start hub, rail, gateway and shops; reset to seed; Ctrl-C stops all."""
import signal
import sys

import httpx

from scripts.services import start_all, stop_all
from shared.config import url
from shared.keys import ensure_keys

if __name__ == "__main__":
    ensure_keys()
    procs = start_all()
    httpx.post(f"{url('hub')}/demo/reset", timeout=10).raise_for_status()
    print("Leash services up:")
    for s in ("hub", "gateway", "rail", "shops"):
        print(f"  {s:<8} {url(s)}")
    print("Seed loaded. Ctrl-C to stop.")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        for p in procs:
            p.wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        stop_all(procs)
