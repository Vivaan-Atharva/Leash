"""Demo key files. Each service only loads the key it owns.

keys/agent.sk     agent's signing key (agent/)
keys/rogue.sk     an unregistered agent key (scenario S8)
keys/phone.sk     seed phone key used to sign Asha's seed mandate (Phase 2 phone makes its own)
keys/gateway.sk   gateway's key: the only key that can move money on wallet R
keys/*.pk         public halves, readable by anyone
"""
from pathlib import Path

from shared.config import keys_dir
from shared.crypto import load_signing_key, new_signing_key, pubkey_b64, save_signing_key

NAMES = ("agent", "rogue", "phone", "gateway")


def ensure_keys(directory: Path | None = None) -> None:
    d = directory or keys_dir()
    for name in NAMES:
        sk_path = d / f"{name}.sk"
        if not sk_path.exists():
            sk = new_signing_key()
            save_signing_key(sk, sk_path)
            (d / f"{name}.pk").write_text(pubkey_b64(sk))


def signing_key(name: str):
    return load_signing_key(keys_dir() / f"{name}.sk")


def public_key(name: str) -> str:
    return (keys_dir() / f"{name}.pk").read_text().strip()
