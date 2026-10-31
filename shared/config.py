"""Ports, URLs and directories. Read from env on every call so tests can override."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_PORTS = {"HUB": 8000, "GATEWAY": 8001, "RAIL": 8002, "SHOPS": 8003}


def port(service: str) -> int:
    service = service.upper()
    return int(os.environ.get(f"LEASH_PORT_{service}", DEFAULT_PORTS[service]))


def url(service: str) -> str:
    service = service.upper()
    explicit = os.environ.get(f"LEASH_{service}_URL")
    if explicit:
        return explicit.rstrip("/")
    host = os.environ.get("LEASH_HOST", "127.0.0.1")
    return f"http://{host}:{port(service)}"


def data_dir() -> Path:
    d = Path(os.environ.get("LEASH_DATA_DIR", ROOT / "data"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def keys_dir() -> Path:
    return Path(os.environ.get("LEASH_KEYS_DIR", ROOT / "keys"))
