export type LeashEvent = {
  seq: number;
  ts: string;
  lane: "left" | "right" | "both" | "system";
  type: string;
  data: Record<string, unknown>;
  backfill?: boolean;
};

/** Hub runs on the same machine as the page, port 8000 (works over the hotspot too). */
export function hubBase(): string {
  const env = process.env.NEXT_PUBLIC_HUB_URL;
  if (env) return env.replace(/\/$/, "");
  const host = typeof window === "undefined" ? "127.0.0.1" : window.location.hostname;
  return `http://${host}:8000`;
}

export function hubWsUrl(): string {
  return hubBase().replace(/^http/, "ws") + "/ws";
}
