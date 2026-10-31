"""ed25519 signing over canonical JSON of an object without its signature field(s)."""
import base64
import secrets
from pathlib import Path
from typing import Iterable

import nacl.exceptions
import nacl.signing

from shared.canonical import canonical_json


def b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def b64d(s: str) -> bytes:
    return base64.b64decode(s, validate=True)


def new_signing_key() -> nacl.signing.SigningKey:
    return nacl.signing.SigningKey.generate()


def pubkey_b64(sk: nacl.signing.SigningKey) -> str:
    return b64e(bytes(sk.verify_key))


def save_signing_key(sk: nacl.signing.SigningKey, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(b64e(bytes(sk)))
    path.chmod(0o600)


def load_signing_key(path: Path) -> nacl.signing.SigningKey:
    return nacl.signing.SigningKey(b64d(path.read_text().strip()))


def _body(obj: dict, field: str, exclude: Iterable[str]) -> dict:
    drop = {field, *exclude}
    return {k: v for k, v in obj.items() if k not in drop}


def sign_obj(obj: dict, sk: nacl.signing.SigningKey, field: str = "signature",
             exclude: Iterable[str] = ()) -> dict:
    """Return a copy of obj with `field` set to the signature of the rest of the object."""
    sig = sk.sign(canonical_json(_body(obj, field, exclude))).signature
    return {**obj, field: b64e(sig)}


def verify_obj(obj: dict, pubkey: str, field: str = "signature",
               exclude: Iterable[str] = ()) -> bool:
    try:
        vk = nacl.signing.VerifyKey(b64d(pubkey))
        vk.verify(canonical_json(_body(obj, field, exclude)), b64d(obj[field]))
        return True
    except (KeyError, ValueError, TypeError, nacl.exceptions.BadSignatureError,
            nacl.exceptions.ValueError, nacl.exceptions.TypeError):
        return False


def random_nonce() -> str:
    return b64e(secrets.token_bytes(16))


def fingerprint(pubkey_or_sig: str) -> str:
    """Short, human-readable id for a key or signature."""
    import hashlib
    return hashlib.sha256(pubkey_or_sig.encode()).hexdigest()[:12]
