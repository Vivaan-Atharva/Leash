"""`make doctor`: is this laptop ready to run the Leash demo? Prints a fix for anything missing."""
import importlib
import json
import shutil
import socket
import subprocess
import sys
import urllib.request

from shared.config import ROOT, keys_dir

G, R, A, O = "\033[32m", "\033[31m", "\033[33m", "\033[0m"
problems = 0


def check(name: str, ok: bool, detail: str = "", fix: str = "", required: bool = True) -> None:
    global problems
    mark = f"{G}✓" if ok else (f"{R}✕" if required else f"{A}!")
    print(f"{mark} {name:<30}{O} {detail}")
    if not ok:
        if fix:
            print(f"    → {fix}")
        problems += required


def run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def http_json(u: str):
    try:
        with urllib.request.urlopen(u, timeout=2) as r:
            return json.load(r)
    except Exception:
        return None


print("Leash doctor\n")
v = sys.version_info
check("Python ≥ 3.11", v >= (3, 11), f"{v.major}.{v.minor}", "install Python 3.11+ (python.org)")
node = run(["node", "--version"])
check("Node ≥ 20", node.startswith("v") and int(node[1:].split(".")[0]) >= 20, node or "missing", "install Node 20+ (nodejs.org)")
missing = [m for m in ("fastapi", "nacl", "httpx", "z3", "matplotlib") if importlib.util.find_spec(m) is None]
check("Python packages", not missing, "all installed" if not missing else f"missing {', '.join(missing)}", "make setup")
check("web dependencies", (ROOT / "web" / "node_modules" / "next").exists(), "", "make setup  (or: cd web && npm install)")
check("demo keys", all((keys_dir() / f"{n}.sk").exists() for n in ("agent", "rogue", "phone", "gateway")), str(keys_dir()), "make keys")
check("web production build", (ROOT / "web" / ".next" / "BUILD_ID").exists(), "", "make web-build (make demo also builds it on first run)", required=False)

from agent.llm import model_name, ollama_url  # noqa: E402
has_ollama = bool(shutil.which("ollama")) or (ROOT.anchor and __import__("os").path.exists("/Applications/Ollama.app"))
check("Ollama installed", has_ollama, shutil.which("ollama") or "", "download from https://ollama.com", required=False)
tags = http_json(f"{ollama_url()}/api/tags")
check("Ollama running", tags is not None, ollama_url(), "open the Ollama app, or run: ollama serve", required=False)
names = [m.get("name", "") for m in (tags or {}).get("models", [])]
check(f"model {model_name()}", any(n.startswith(model_name().split(":")[0]) for n in names),
      ", ".join(names) or "none pulled", f"ollama pull {model_name()}", required=False)

for name, port in (("hub", 8000), ("gateway", 8001), ("rail", 8002), ("shops", 8003), ("web", 3000)):
    s = socket.socket()
    s.settimeout(0.3)
    busy = s.connect_ex(("127.0.0.1", port)) == 0
    s.close()
    ours = busy and (http_json(f"http://127.0.0.1:{port}/health") or {}).get("service") == name if port != 3000 else busy
    check(f"port {port} ({name})", not busy or ours, "free" if not busy else "Leash is running" if ours else "used by something else",
          f"free port {port} (lsof -i :{port})")

du = shutil.disk_usage(ROOT)
check("disk space", du.free > 3 * 1024**3, f"{du.free // 1024**3} GB free", "free up a few GB (models are 2–5 GB)")
batt = run(["pmset", "-g", "batt"])
if batt:
    check("on power", "AC Power" in batt, "plugged in" if "AC Power" in batt else "on battery", "plug in for the demo", required=False)
golden = sorted(p.stem for p in (ROOT / "traces" / "golden").glob("S*.json"))
check("golden traces S0–S5", all(f"S{i}" in golden for i in range(6)), ", ".join(golden) or "none",
      "with the model ready: make dev (one terminal) then make golden", required=False)

print(f"\n{G}Ready for `make demo`.{O}" if not problems else f"\n{R}{problems} thing(s) to fix first.{O}")
sys.exit(1 if problems else 0)
