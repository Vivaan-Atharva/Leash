import hashlib
import random

from gateway import merkle as M


def leaves(n):
    return [M.leaf_hash(f"entry {i}".encode()) for i in range(n)]


def test_rfc6962_shape():
    l = leaves(3)
    assert M.root(l) == M.node_hash(M.node_hash(l[0], l[1]), l[2])
    assert M.root([]) == hashlib.sha256(b"").digest()


def test_every_proof_verifies_for_every_size():
    for n in range(1, 40):
        ls = leaves(n)
        r = M.root(ls)
        for m in range(n):
            assert M.verify_inclusion(m, n, ls[m], M.inclusion_proof(m, ls), r), (m, n)


def test_tampered_leaf_or_wrong_root_fails():
    ls = leaves(17)
    r = M.root(ls)
    rng = random.Random(1)
    for _ in range(50):
        m = rng.randrange(17)
        proof = M.inclusion_proof(m, ls)
        assert not M.verify_inclusion(m, 17, M.leaf_hash(b"changed"), proof, r)
        assert not M.verify_inclusion(m, 17, ls[m], proof, M.leaf_hash(b"other root"))
        assert not M.verify_inclusion((m + 1) % 17, 17, ls[m], proof, r) or ls[m] == ls[(m + 1) % 17]
