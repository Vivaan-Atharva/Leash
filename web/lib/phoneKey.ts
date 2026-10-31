"use client";
/** Asha's phone key: ed25519 made in the browser (tweetnacl), kept in localStorage. */
import nacl from "tweetnacl";
import { canonicalBytes } from "./canonical";

const KEY = "leash.phone.sk.v1";

export function b64(bytes: Uint8Array): string {
  let s = "";
  bytes.forEach((b) => (s += String.fromCharCode(b)));
  return btoa(s);
}

export function unb64(s: string): Uint8Array {
  return Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
}

export function phoneKeyPair(): nacl.SignKeyPair {
  let stored: string | null = null;
  try {
    stored = localStorage.getItem(KEY);
  } catch {}
  if (stored) return nacl.sign.keyPair.fromSecretKey(unb64(stored));
  const kp = nacl.sign.keyPair();
  try {
    localStorage.setItem(KEY, b64(kp.secretKey));
  } catch {}
  return kp;
}

export function phonePubkey(): string {
  return b64(phoneKeyPair().publicKey);
}

/** Sign obj (without its signature field) exactly like shared/crypto.py sign_obj. */
export function signObj<T extends Record<string, unknown>>(obj: T): T & { signature: string } {
  const { signature: _drop, ...body } = obj as Record<string, unknown>; // eslint-disable-line @typescript-eslint/no-unused-vars
  const sig = nacl.sign.detached(canonicalBytes(body), phoneKeyPair().secretKey);
  return { ...(obj as T), signature: b64(sig) };
}
