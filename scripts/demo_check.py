"""`make demo-check`: preflight every dependency; exit non-zero if anything required is red."""
import sys

import httpx

from shared.config import url

GREEN, RED, AMBER, OFF = "\033[32m", "\033[31m", "\033[33m", "\033[0m"

if __name__ == "__main__":
    try:
        pf = httpx.get(f"{url('hub')}/preflight", timeout=10).json()
    except httpx.HTTPError:
        print(f"{RED}✕ hub not reachable at {url('hub')}. Start services with `make dev`.{OFF}")
        sys.exit(1)
    for i in pf["items"]:
        mark = f"{GREEN}✓" if i["ok"] else (f"{RED}✕" if i["required"] else f"{AMBER}!")
        print(f"{mark} {i['name']:<24}{OFF} {i['detail']}")
    print(f"\n{GREEN}demo-check passed{OFF}" if pf["ok"] else f"\n{RED}demo-check FAILED{OFF}")
    sys.exit(0 if pf["ok"] else 1)
