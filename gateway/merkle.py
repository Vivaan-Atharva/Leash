"""Merkle tree log with inclusion proofs, as in Certificate Transparency (RFC 6962 / RFC 9162).

leaf hash  = SHA-256(0x00 || leaf bytes)          leaf bytes = canonical JSON of the log entry body
node hash  = SHA-256(0x01 || left || right)
tree head  = {tree_size, root_hash, timestamp}, signed by the gateway after every append

A report carries an inclusion proof for its decision. Anyone (the report page does it in the browser)
can recompute the leaf from the entry, walk the proof to the root, and check the gateway's signature
on the tree head. Change one byte of the entry and the leaf, and so the root, no longer match.
"""
import hashlib

from shared.canonical import canonical_json


def _h(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def leaf_bytes(index: int, timestamp: str, type_: str, payload: dict, prev_hash: str) -> bytes:
    return canonical_json({"index": index, "timestamp": timestamp, "type": type_,
                           "payload": payload, "prev_hash": prev_hash})


def leaf_hash(data: bytes) -> bytes:
    return _h(b"\x00" + data)


def node_hash(left: bytes, right: bytes) -> bytes:
    return _h(b"\x01" + left + right)


def _split(n: int) -> int:
    """Largest power of two strictly smaller than n (n > 1)."""
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def root(leaves: list[bytes]) -> bytes:
    """MTH over leaf hashes (RFC 6962 §2.1)."""
    n = len(leaves)
    if n == 0:
        return _h(b"")
    if n == 1:
        return leaves[0]
    k = _split(n)
    return node_hash(root(leaves[:k]), root(leaves[k:]))


def inclusion_proof(m: int, leaves: list[bytes]) -> list[bytes]:
    """PATH(m, D[n]) (RFC 6962 §2.1.1): sibling hashes from leaf m up to the root."""
    n = len(leaves)
    if n <= 1:
        return []
    k = _split(n)
    if m < k:
        return inclusion_proof(m, leaves[:k]) + [root(leaves[k:])]
    return inclusion_proof(m - k, leaves[k:]) + [root(leaves[:k])]


def verify_inclusion(index: int, size: int, leaf: bytes, proof: list[bytes], expected_root: bytes) -> bool:
    """RFC 9162 §2.1.3.2 verification."""
    if index >= size:
        return False
    fn, sn, r = index, size - 1, leaf
    for p in proof:
        if sn == 0:
            return False
        if fn & 1 or fn == sn:
            r = node_hash(p, r)
            if not fn & 1:
                while fn & 1 == 0 and fn != 0:
                    fn >>= 1
                    sn >>= 1
        else:
            r = node_hash(r, p)
        fn >>= 1
        sn >>= 1
    return sn == 0 and r == expected_root
