/** Canonical JSON, byte-identical to shared/canonical.py: sorted keys, no whitespace, UTF-8, no floats. */
export function canonical(v: unknown): string {
  if (v === null || typeof v === "boolean" || typeof v === "string") return JSON.stringify(v);
  if (typeof v === "number") {
    if (!Number.isInteger(v)) throw new Error(`floats are not allowed in signed objects: ${v}`);
    return String(v);
  }
  if (Array.isArray(v)) return "[" + v.map(canonical).join(",") + "]";
  if (typeof v === "object") {
    const o = v as Record<string, unknown>;
    // Python sorts by code point; for our ASCII keys this equals JS's default sort.
    const keys = Object.keys(o).filter((k) => o[k] !== undefined).sort();
    return "{" + keys.map((k) => JSON.stringify(k) + ":" + canonical(o[k])).join(",") + "}";
  }
  throw new Error(`cannot canonicalise ${typeof v}`);
}

export function canonicalBytes(v: unknown): Uint8Array {
  return new TextEncoder().encode(canonical(v));
}
