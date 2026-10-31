export type Lane = "left" | "right" | "both" | "system";
export type LeashEvent = {
  seq: number;
  ts: string;
  lane: Lane;
  type: string;
  data: Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  backfill?: boolean;
};

/** REST goes through Next rewrites (/api/hub, /api/gateway, /api/rail). */
export const api = {
  hub: (p: string) => `/api/hub${p}`,
  gateway: (p: string) => `/api/gateway${p}`,
  rail: (p: string) => `/api/rail${p}`,
};

export async function getJSON<T = any>(path: string): Promise<T> { // eslint-disable-line @typescript-eslint/no-explicit-any
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

export async function postJSON<T = any>(path: string, body?: unknown): Promise<T> { // eslint-disable-line @typescript-eslint/no-explicit-any
  const r = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: body === undefined ? "{}" : JSON.stringify(body),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail ?? `${path}: ${r.status}`);
  return j;
}

/** The hub WebSocket is on the same host as the page, port 8000. */
export function hubWsUrl(): string {
  const env = process.env.NEXT_PUBLIC_HUB_WS;
  if (env) return env;
  const proto = typeof window !== "undefined" && window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.hostname}:8000/ws`;
}
