/** RFC 6962 / 9162 inclusion-proof verification, in the browser. Mirrors gateway/merkle.py. */
import { sha256 } from "@noble/hashes/sha256";
import nacl from "tweetnacl";
import { canonicalBytes } from "./canonical";
import { unb64 } from "./phoneKey";

const hex = (b: Uint8Array) => Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
const unhex = (s: string) => Uint8Array.from(s.match(/../g) ?? [], (x) => parseInt(x, 16));
const cat = (...parts: Uint8Array[]) => {
  const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let i = 0;
  for (const p of parts) {
    out.set(p, i);
    i += p.length;
  }
  return out;
};

export const leafHash = (entry: unknown) => sha256(cat(new Uint8Array([0]), canonicalBytes(entry)));
const nodeHash = (l: Uint8Array, r: Uint8Array) => sha256(cat(new Uint8Array([1]), l, r));

export function verifyInclusion(index: number, size: number, leaf: Uint8Array, proof: string[], root: string): boolean {
  if (index >= size) return false;
  let fn = index, sn = size - 1, r = leaf;
  for (const h of proof) {
    const p = unhex(h);
    if (sn === 0) return false;
    if (fn & 1 || fn === sn) {
      r = nodeHash(p, r);
      if (!(fn & 1)) while (!(fn & 1) && fn !== 0) { fn >>= 1; sn >>= 1; }
    } else r = nodeHash(r, p);
    fn >>= 1;
    sn >>= 1;
  }
  return sn === 0 && hex(r) === root;
}

export type MerkleBundle = {
  leaf_index: number;
  entry: { index: number; timestamp: string; type: string; payload: unknown; prev_hash: string } | null;
  proof: string[];
  sth: { tree_size: number; root_hash: string; timestamp: string; signature: string };
  gateway_pubkey: string;
};

/** Everything checked locally: leaf recomputed from the entry, path to the root, gateway signature on the tree head. */
export function verifyBundle(m: MerkleBundle) {
  const leaf = m.entry ? leafHash(m.entry) : new Uint8Array();
  const included = !!m.entry && verifyInclusion(m.leaf_index, m.sth.tree_size, leaf, m.proof, m.sth.root_hash);
  const { signature, ...head } = m.sth;
  let signed = false;
  try {
    signed = nacl.sign.detached.verify(canonicalBytes(head), unb64(signature), unb64(m.gateway_pubkey));
  } catch {}
  return { leaf: hex(leaf), included, signed };
}
