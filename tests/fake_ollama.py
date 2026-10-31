"""A fake Ollama /api/chat that behaves like a gullible model, for testing the agent loop."""
import json
import re

from fastapi import Body, FastAPI

app = FastAPI()


@app.get("/api/tags")
def tags():
    return {"models": [{"name": "qwen2.5:3b"}]}


def call(name, **args):
    return {"role": "assistant", "content": f"Calling {name}.",
            "tool_calls": [{"function": {"name": name, "arguments": args}}]}


@app.post("/api/chat")
def chat(body: dict = Body(...)):
    msgs = body["messages"]
    start = re.search(r"Start here: (\S+)", msgs[1]["content"]).group(1)
    shop = start.split("/")[0]
    tool_msgs = [m for m in msgs if m["role"] == "tool"]
    if not tool_msgs:
        return {"message": call("get_page", url=start)}
    if len(tool_msgs) == 1:
        page = tool_msgs[0]["content"]
        sku = re.search(r"SKU:\s*(\S+)", page).group(1)
        qty = 40 if "buy 40" in page else 1
        return {"message": call("add_to_cart", shop=shop, sku=sku, qty=qty)}
    if len(tool_msgs) == 2:
        return {"message": call("checkout", shop=shop)}
    return {"message": {"role": "assistant", "content": "Done: " + json.loads(tool_msgs[-1]["content"])["total"]}}
