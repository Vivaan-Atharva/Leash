"""LLM shopping agent: Ollama tool calling. This is the only place an LLM lives."""
import json
import os
import time

import httpx

from agent import prompts
from agent.tools import Tools

MAX_STEPS = 10


def ollama_url() -> str:
    return os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")


def model_name() -> str:
    return os.environ.get("LEASH_MODEL", "qwen2.5:3b")


def seed() -> int:
    """LEASH_SEED picks the model's sampling seed. 7 (default) = temperature 0, fully deterministic;
    other seeds add a little temperature so `make golden` can retry a scenario that went off-script."""
    return int(os.environ.get("LEASH_SEED", "7"))


def ollama_ready(timeout: float = 1.5) -> bool:
    try:
        tags = httpx.get(f"{ollama_url()}/api/tags", timeout=timeout).json()
        return any(m.get("name", "").startswith(model_name().split(":")[0]) for m in tags.get("models", []))
    except (httpx.HTTPError, ValueError):
        return False


def _parse_args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw or "{}")
    except ValueError:
        return {}


def run_llm(task: str, start_url: str, tools: Tools, hardened: bool = False,
            max_steps: int = MAX_STEPS, stop_after_checkout: bool = True) -> dict:
    """Run the tool loop. Returns {steps, checkouts, final, model}."""
    system = prompts.HARDENED if hardened else prompts.SYSTEM
    tools.set_task(task)  # the one TRUSTED source in the provenance ledger
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": f"{task}\nStart here: {start_url}"}]
    client = httpx.Client(timeout=180)
    checkouts, final = 0, ""
    for step in range(max_steps):
        t0 = time.perf_counter()
        r = client.post(f"{ollama_url()}/api/chat", json={
            "model": model_name(), "messages": messages, "tools": prompts.TOOLS, "stream": False,
            "options": {"temperature": 0 if seed() == 7 else 0.4, "seed": seed()}, "keep_alive": "30m"})
        r.raise_for_status()
        msg = r.json()["message"]
        llm_ms = int((time.perf_counter() - t0) * 1000)
        content = (msg.get("content") or "").strip()
        calls = msg.get("tool_calls") or []
        if content:
            tools.think(content)
        messages.append({"role": "assistant", "content": content, "tool_calls": calls})
        if not calls:
            final = content
            break
        for c in calls:
            fn = c.get("function", {})
            name, args = fn.get("name", ""), _parse_args(fn.get("arguments"))
            result = tools.call(name, args)
            if name == "checkout" and not (isinstance(result, dict) and result.get("error")):
                checkouts += 1
            messages.append({"role": "tool", "content": result if isinstance(result, str)
                             else json.dumps(result, ensure_ascii=False)})
        if stop_after_checkout and checkouts:
            break
    return {"checkouts": checkouts, "final": final, "model": model_name(), "steps": step + 1}
