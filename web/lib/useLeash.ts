"use client";
/** Mission Control state: one reducer fed by hub events (WebSocket) plus a REST snapshot. */
import { useCallback, useEffect, useReducer, useRef } from "react";
import { api, getJSON, hubWsUrl, type LeashEvent } from "./hub";

export type Check = { n: number; name: string; pass: boolean; detail: string };
export type Decision = {
  decision_id: string;
  request_id: string;
  outcome: "ALLOWED" | "BLOCKED" | "HELD";
  amount_paise: number;
  decided_in_us: number;
  failing: number[];
  reasons: string[];
  merchant: string;
  checks: Check[];
  log_index?: number;
  seq: number;
};
export type Payment = { id: string; amount_paise: number; merchant: string; request_id: string; seq: number };
export type Line = { id: number; kind: "thought" | "tool" | "result" | "system"; text: string };
export type ChainEntry = { index: number; type: string; hash: string };
export type MandateInfo = {
  mandate_id: string;
  user: string;
  per_order_paise: number;
  per_week_paise: number;
  status: "ACTIVE" | "REVOKED";
  revoked_at: string | null;
  phone_pubkey: string;
  merchants: string[];
};
export type Director = {
  index: number;
  moment: string | null;
  status: string | null;
  text?: string;
  scenario?: string;
  name?: string;
  task?: string;
};

export type State = {
  connected: boolean;
  mode: string; // LIVE | REPLAY | SCRIPTED
  model: string | null;
  left: { balance: number | null; payments: Payment[] };
  right: { balance: number | null; decision: Decision | null; decisions: Decision[]; pending: string | null };
  score: { left_lost_paise: number; right_lost_paise: number; left_paid_paise: number; right_paid_paise: number };
  lines: Line[];
  shop: { url: string | null; name?: string; merchant?: string; injections: { style: string; label: string }[] };
  cart: { request_id: string; merchant: string; amount: string; items: { sku: string; qty: number; brand: string; family: string }[] } | null;
  packet: { id: string; seq: number } | null;
  chain: ChainEntry[];
  verify: { ok: boolean; broken_at: number | null; length: number } | null;
  tampered: boolean;
  mandate: MandateInfo | null;
  revokeSeq: number | null;
  director: Director;
  resetSeq: number;
};

const initial: State = {
  connected: false,
  mode: "LIVE",
  model: null,
  left: { balance: null, payments: [] },
  right: { balance: null, decision: null, decisions: [], pending: null },
  score: { left_lost_paise: 0, right_lost_paise: 0, left_paid_paise: 0, right_paid_paise: 0 },
  lines: [],
  shop: { url: null, injections: [] },
  cart: null,
  packet: null,
  chain: [],
  verify: null,
  tampered: false,
  mandate: null,
  revokeSeq: null,
  director: { index: -1, moment: null, status: null },
  resetSeq: 0,
};

type Action =
  | { t: "event"; e: LeashEvent }
  | { t: "connected"; v: boolean }
  | { t: "snapshot"; s: Partial<State> }
  | { t: "mandate"; m: MandateInfo | null };

let lineId = 0;
const line = (kind: Line["kind"], text: string): Line => ({ id: ++lineId, kind, text });

function fmtArgs(a: Record<string, unknown>): string {
  return Object.entries(a ?? {})
    .map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`)
    .join(", ");
}

function reduce(s: State, a: Action): State {
  if (a.t === "connected") return { ...s, connected: a.v };
  if (a.t === "snapshot") return { ...s, ...a.s };
  if (a.t === "mandate") return { ...s, mandate: a.m };
  const { e } = a;
  const d = e.data;
  switch (e.type) {
    case "system.mode":
      if (d.reset) return { ...initial, connected: s.connected, mode: d.mode ?? s.mode, resetSeq: e.seq, mandate: s.mandate };
      return { ...s, mode: d.mode ?? s.mode, model: d.model !== undefined ? d.model : s.model };
    case "score.update":
      return { ...s, score: { ...s.score, ...d } };
    case "director.moment": {
      const director = { ...s.director, ...d, index: d.index ?? s.director.index } as Director;
      if (d.status === "starting" || (d.status === "running" && s.director.status !== "starting")) {
        return { ...s, director, lines: [line("system", `▶ ${d.scenario ?? d.moment}${d.name ? " · " + d.name : ""}`)], cart: null };
      }
      if (d.status === "running" && d.task) {
        return { ...s, director, lines: [...s.lines, line("system", `Task: ${d.task}`)] };
      }
      return { ...s, director };
    }
    case "agent.thought":
      return { ...s, lines: [...s.lines, line("thought", d.text)].slice(-60) };
    case "agent.tool_call":
      return { ...s, lines: [...s.lines, line("tool", `${d.tool}(${fmtArgs(d.args)})`)].slice(-60) };
    case "agent.tool_result":
      if (d.tool !== "checkout" && !d.result?.error) return s;
      return { ...s, lines: [...s.lines, line("result", d.result?.error ? `✕ ${d.result.error}` : `→ submitted ${d.result?.total ?? ""}`)].slice(-60) };
    case "shop.page_viewed":
      return { ...s, shop: { url: `/shop${d.url}?view=1`, name: d.name, merchant: d.merchant, injections: d.injections ?? [] } };
    case "request.created":
      return {
        ...s,
        cart: { request_id: d.request_id, merchant: d.merchant, amount: d.amount, items: d.cart ?? [] },
        packet: e.backfill ? s.packet : { id: d.request_id, seq: e.seq },
        right: { ...s.right, pending: d.request_id },
      };
    case "gateway.decision": {
      const dec = { ...(d as Decision), seq: e.seq };
      return { ...s, right: { ...s.right, decision: dec, decisions: [dec, ...s.right.decisions].slice(0, 20), pending: null } };
    }
    case "rail.debit":
      if (e.lane === "left") {
        const p = { id: d.debit_id, amount_paise: d.amount_paise, merchant: d.merchant, request_id: d.request_id, seq: e.seq };
        return { ...s, left: { ...s.left, payments: [p, ...s.left.payments].slice(0, 12) } };
      }
      return s;
    case "rail.balance":
      if (e.lane === "left") return { ...s, left: { ...s.left, balance: d.balance_paise } };
      if (e.lane === "right") return { ...s, right: { ...s.right, balance: d.balance_paise } };
      return s;
    case "mandate.revoked":
      return {
        ...s,
        revokeSeq: e.backfill ? s.revokeSeq : e.seq,
        mandate: s.mandate ? { ...s.mandate, status: "REVOKED", revoked_at: d.revoked_at } : s.mandate,
      };
    case "log.appended":
      if (s.chain.some((c) => c.index === d.index)) return s;
      return { ...s, chain: [...s.chain, { index: d.index, type: d.type, hash: d.hash }].slice(-40) };
    case "log.tampered":
      return { ...s, tampered: !!d.tampered, verify: { ok: d.ok, broken_at: d.broken_at, length: d.length } };
    default:
      return s;
  }
}

export function toMandateInfo(r: any): MandateInfo | null { // eslint-disable-line @typescript-eslint/no-explicit-any
  if (!r?.mandate) return null;
  const m = r.mandate;
  return {
    mandate_id: m.mandate_id,
    user: m.user.name,
    per_order_paise: m.limits.per_order_paise,
    per_week_paise: m.limits.per_week_paise,
    status: r.status,
    revoked_at: r.revoked_at,
    phone_pubkey: m.user.phone_pubkey,
    merchants: m.allowed_merchants,
  };
}

export function useLeash() {
  const [state, dispatch] = useReducer(reduce, initial);
  const lastSeq = useRef(0);

  const refresh = useCallback(async () => {
    const [wallets, mandate, log, verify, score, hub] = await Promise.allSettled([
      getJSON(api.rail("/wallets")),
      getJSON(api.gateway("/mandates/current")),
      getJSON(api.gateway("/log?from_=1&limit=500")),
      getJSON(api.gateway("/log/verify")),
      getJSON(api.hub("/score")),
      getJSON(api.hub("/health")),
    ]);
    const snap: Partial<State> = {};
    if (wallets.status === "fulfilled") {
      snap.left = { balance: wallets.value.L?.balance_paise ?? null, payments: [] };
      snap.right = { balance: wallets.value.R?.balance_paise ?? null, decision: null, decisions: [], pending: null };
    }
    if (log.status === "fulfilled")
      snap.chain = log.value.entries.slice(-40).map((x: any) => ({ index: x.index, type: x.type, hash: x.hash })); // eslint-disable-line @typescript-eslint/no-explicit-any
    if (verify.status === "fulfilled") snap.verify = verify.value;
    if (score.status === "fulfilled") snap.score = score.value;
    if (hub.status === "fulfilled") snap.mode = hub.value.mode;
    dispatch({ t: "snapshot", s: snap });
    dispatch({ t: "mandate", m: mandate.status === "fulfilled" ? toMandateInfo(mandate.value) : null });
  }, []);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const connect = () => {
      ws = new WebSocket(hubWsUrl());
      ws.onopen = () => {
        dispatch({ t: "connected", v: true });
        refresh();
      };
      ws.onmessage = (m) => {
        const e = JSON.parse(m.data) as LeashEvent;
        if (e.backfill && e.seq <= lastSeq.current) return; // already seen before a reconnect
        lastSeq.current = e.seq;
        // Backfilled events rebuild text state but must not replay animations.
        if (e.backfill && ["request.created", "mandate.revoked"].includes(e.type)) return;
        dispatch({ t: "event", e });
        if (e.type === "mandate.signed" || (e.type === "system.mode" && e.data.reset)) refresh();
      };
      ws.onclose = () => {
        dispatch({ t: "connected", v: false });
        if (!stopped) timer = setTimeout(connect, 1000);
      };
    };
    connect();
    const ping = setInterval(() => ws?.readyState === 1 && ws.send("ping"), 15000);
    return () => {
      stopped = true;
      clearInterval(ping);
      clearTimeout(timer);
      ws?.close();
    };
  }, [refresh]);

  return { state, refresh };
}
