"use client";

import { AnimatePresence, motion, useMotionValue, useTransform, animate } from "framer-motion";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, getJSON, hubWsUrl, postJSON, type LeashEvent } from "@/lib/hub";
import { friendly, shopName as shopNameOf } from "@/lib/friendly";
import { inr } from "@/lib/money";
import { phonePubkey, signObj } from "@/lib/phoneKey";

type Item = { family: string; label: string; max_qty: number; brands: string[]; substitutes_ok: boolean };
type FeedCard = { id: string; ok: boolean; text: string; amount: number; seq: number; held?: boolean };
type HeldReq = { decision_id: string; merchant: string; amount: string; reason: string; expires_at: string;
  items: { brand: string; family: string; qty: number; unit: string }[] };

const CATEGORIES = [
  { id: "dairy", label: "Dairy" },
  { id: "bakery", label: "Bakery" },
  { id: "staples", label: "Staples" },
];
const SHOPS = [
  { id: "freshcart.in", label: "FreshCart" },
  { id: "dailybasket.in", label: "DailyBasket" },
];
const DEFAULT_ITEMS: Item[] = [
  { family: "milk", label: "Milk", max_qty: 2, brands: ["Amul", "Nandini"], substitutes_ok: true },
  { family: "bread", label: "Bread", max_qty: 1, brands: ["Modern", "Britannia"], substitutes_ok: true },
  { family: "butter", label: "Butter", max_qty: 1, brands: ["Amul"], substitutes_ok: false },
];

const isoSec = (ms: number) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z");
const hex = (n: number) => Array.from(crypto.getRandomValues(new Uint8Array(n)), (b) => b.toString(16).padStart(2, "0")).join("");

export default function Phone() {
  const [pub, setPub] = useState<string | null>(null);
  const [current, setCurrent] = useState<any>(null); // eslint-disable-line @typescript-eslint/no-explicit-any
  const [view, setView] = useState<"setup" | "live">("setup");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const c = await getJSON(api.gateway("/mandates/current"));
      setCurrent(c);
      return c;
    } catch {
      setCurrent(null);
      return null;
    }
  }, []);

  useEffect(() => {
    const p = phonePubkey();
    setPub(p);
    load().then((c) => c?.mandate?.user?.phone_pubkey === p && setView("live"));
  }, [load]);

  const mine = !!current && current.mandate.user.phone_pubkey === pub;

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col px-5 pb-10 pt-6 text-[17px]">
      <div className="mb-5 flex items-center justify-between">
        <span className="text-2xl font-black tracking-[0.18em] text-white">LEASH</span>
        <div className="flex gap-1 rounded-full border border-line p-1 text-sm">
          {(["setup", "live"] as const).map((v) => (
            <button key={v} onClick={() => setView(v)}
              className={`rounded-full px-3 py-1 ${view === v ? "bg-accent font-bold text-bg" : "text-muted"}`}>
              {v === "setup" ? "Mandate" : "Live"}
            </button>
          ))}
        </div>
      </div>
      {error && <div className="mb-4 rounded-xl border border-danger bg-danger/10 p-3 text-danger">{error}</div>}
      {view === "setup" ? (
        <Setup pub={pub} onSigned={async () => { setError(null); await load(); setView("live"); }} onError={setError} />
      ) : (
        <Live current={current} mine={mine} reload={load} onError={setError} onNew={() => setView("setup")} />
      )}
    </main>
  );
}

// ------------------------------------------------------------------ setup
function Setup({ pub, onSigned, onError }: { pub: string | null; onSigned: () => void; onError: (e: string) => void }) {
  const [cats, setCats] = useState<string[]>(["dairy", "bakery", "staples"]);
  const [shops, setShops] = useState<string[]>(SHOPS.map((s) => s.id));
  const [perOrder, setPerOrder] = useState(150);
  const [perWeek, setPerWeek] = useState(500);
  const [items, setItems] = useState<Item[]>(DEFAULT_ITEMS);
  const [busy, setBusy] = useState(false);
  const toggle = (list: string[], v: string) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

  const sign = async () => {
    if (!pub) return;
    setBusy(true);
    try {
      const [{ agent_pubkey }, { now }] = await Promise.all([getJSON(api.gateway("/agents/current")), getJSON(api.gateway("/time"))]);
      const t = Date.parse(now);
      const mandate = signObj({
        mandate_id: `mdt_${hex(2)}`,
        user: { id: "usr_asha", name: "Asha", phone_pubkey: pub },
        agent_pubkey,
        reserve_block_id: "blk_r_01",
        allowed_merchants: shops,
        allowed_categories: cats,
        limits: { per_order_paise: perOrder * 100, per_week_paise: perWeek * 100 },
        intent: { items: items.map(({ family, max_qty, brands, substitutes_ok }) => ({ family, max_qty, brands, substitutes_ok })) },
        price_band_pct: 15,
        step_up: { new_brand: true, order_over_pct_of_cap: 70 },
        valid_from: isoSec(t - 3600_000),
        valid_until: isoSec(t + 7 * 24 * 3600_000),
      });
      await postJSON(api.gateway("/mandates"), mandate);
      onSigned();
    } catch (e) {
      onError(`Couldn't sign: ${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-3xl font-bold text-white">Set Asha&apos;s leash</h1>
      <Field label="What it may buy">
        <div className="flex flex-wrap gap-2">
          {CATEGORIES.map((c) => (
            <button key={c.id} onClick={() => setCats(toggle(cats, c.id))}
              className={`rounded-full border-2 px-4 py-2 font-semibold ${cats.includes(c.id) ? "border-accent bg-accent/15 text-accent" : "border-line text-muted"}`}>
              {c.label}
            </button>
          ))}
        </div>
      </Field>
      <Slider label="Per order" value={perOrder} min={50} max={500} step={10} onChange={setPerOrder} />
      <Slider label="Per week" value={perWeek} min={100} max={2000} step={50} onChange={setPerWeek} />
      <Field label="Shops">
        {SHOPS.map((s) => (
          <label key={s.id} className="flex items-center justify-between rounded-xl border border-line bg-surface px-4 py-3">
            <span><span className="font-semibold text-white">{s.label}</span> <span className="font-mono text-sm text-muted">{s.id}</span></span>
            <input type="checkbox" className="h-6 w-6 accent-[#2ECDDB]" checked={shops.includes(s.id)} onChange={() => setShops(toggle(shops, s.id))} />
          </label>
        ))}
      </Field>
      <Field label="Shopping list">
        {items.map((it, i) => (
          <div key={it.family} className="flex items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3">
            <div className="flex-1">
              <div className="font-semibold text-white">{it.label}</div>
              <div className="text-sm text-muted">{it.brands.join(" / ")}{it.substitutes_ok ? " · substitutes ok" : ""}</div>
            </div>
            <Stepper value={it.max_qty} onChange={(v) => setItems(items.map((x, j) => (j === i ? { ...x, max_qty: v } : x)))} />
          </div>
        ))}
      </Field>
      <button onClick={sign} disabled={busy || !pub || shops.length === 0}
        className="rounded-2xl bg-accent py-5 text-xl font-black text-bg glow-accent disabled:opacity-50">
        {busy ? "Signing…" : "Sign with this phone"}
      </button>
      <p className="text-center font-mono text-xs text-muted">phone key {pub ? pub.slice(0, 12) + "…" : "…"} · made in this browser, never leaves it</p>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="text-sm font-semibold uppercase tracking-widest text-muted">{label}</div>
      {children}
    </div>
  );
}

function Slider({ label, value, min, max, step, onChange }: { label: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void }) {
  return (
    <Field label={label}>
      <div className="flex items-center gap-4">
        <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} className="h-3 flex-1 accent-[#2ECDDB]" />
        <span className="w-24 text-right font-mono text-2xl font-bold text-white">₹{value}</span>
      </div>
    </Field>
  );
}

function Stepper({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div className="flex items-center gap-2">
      <button onClick={() => onChange(Math.max(1, value - 1))} className="h-11 w-11 rounded-full border border-line text-2xl text-white">−</button>
      <span className="w-8 text-center font-mono text-xl text-white">×{value}</span>
      <button onClick={() => onChange(Math.min(9, value + 1))} className="h-11 w-11 rounded-full border border-line text-2xl text-white">+</button>
    </div>
  );
}

// ------------------------------------------------------------------ live
function Live({ current, mine, reload, onError, onNew }: {
  current: any; mine: boolean; reload: () => Promise<any>; onError: (e: string) => void; onNew: () => void; // eslint-disable-line @typescript-eslint/no-explicit-any
}) {
  const [feed, setFeed] = useState<FeedCard[]>([]);
  const [spent, setSpent] = useState(0);
  const [held, setHeld] = useState<HeldReq | null>(null);
  const mandateId = current?.mandate?.mandate_id;
  const revoked = current?.status === "REVOKED";
  const cap = current?.mandate?.limits?.per_week_paise ?? 50000;

  useEffect(() => {
    let ws: WebSocket | null = null;
    let stop = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const seen = new Set<string>();
    const connect = () => {
      ws = new WebSocket(hubWsUrl());
      ws.onmessage = (m) => {
        const e = JSON.parse(m.data) as LeashEvent;
        if (e.type === "system.mode" && e.data.reset) {
          setFeed([]); setSpent(0); seen.clear(); reload();
        }
        if (e.type === "mandate.revoked" || e.type === "mandate.signed") reload();
        if (e.type === "stepup.requested") setHeld(e.data as HeldReq);
        if (e.type === "stepup.resolved") {
          setHeld((h) => (h && h.decision_id === e.data.decision_id ? null : h));
          const ok = e.data.outcome === "ALLOWED";
          setFeed((f) => f.map((c) => (c.id === e.data.decision_id
            ? { ...c, ok, text: ok ? `Approved ${e.data.amount} · you said yes` : e.data.by === "phone" ? "Denied · you said no" : "Denied · no answer in 60 s" }
            : c)));
          if (ok) setSpent((s) => s + e.data.amount_paise);
        }
        if (e.type !== "gateway.decision" || seen.has(e.data.decision_id)) return;
        seen.add(e.data.decision_id);
        const ok = e.data.outcome === "ALLOWED";
        if (e.data.outcome === "HELD") {
          setFeed((f) => [{ id: e.data.decision_id, ok: true, held: true, text: "Waiting for your approval", amount: 0, seq: e.seq }, ...f].slice(0, 30));
          return;
        }
        setFeed((f) => [{ id: e.data.decision_id, ok, text: friendly(e.data as never), amount: e.data.amount_paise, seq: e.seq }, ...f].slice(0, 30));
        if (ok) setSpent((s) => s + e.data.amount_paise);
      };
      ws.onclose = () => { if (!stop) timer = setTimeout(connect, 1000); };
    };
    connect();
    const beat = setInterval(() => postJSON(api.hub("/phone/heartbeat")).catch(() => {}), 4000);
    postJSON(api.hub("/phone/heartbeat")).catch(() => {});
    return () => { stop = true; clearTimeout(timer); clearInterval(beat); ws?.close(); };
  }, [reload, mandateId]);

  const revoke = async () => {
    try {
      await postJSON(api.gateway(`/mandates/${mandateId}/revoke`), signObj({ mandate_id: mandateId, action: "revoke", ts: new Date().toISOString().replace(/\.\d{3}Z$/, "Z") }));
      await reload();
    } catch (e) {
      onError(`Couldn't revoke: ${e instanceof Error ? e.message : e}`);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-3xl font-bold text-white">{revoked ? "Leash pulled" : "Your assistant is shopping"}</h1>
      {!mine && current && (
        <div className="rounded-xl border border-warn/60 bg-warn/10 p-3 text-sm text-warn">
          The active mandate was signed on another device, so this phone can&apos;t revoke it.{" "}
          <button className="font-bold underline" onClick={onNew}>Sign a new one here</button>
        </div>
      )}
      <div className="rounded-2xl border border-line bg-surface p-4">
        <div className="flex items-baseline justify-between">
          <span className="text-muted">Spent this week</span>
          <span className="font-mono text-xl text-white"><b>{inr(spent)}</b> of {inr(cap)}</span>
        </div>
        <div className="mt-3 h-3 overflow-hidden rounded-full bg-bg">
          <motion.div className="h-full rounded-full bg-accent" animate={{ width: `${Math.min(100, (spent / cap) * 100)}%` }} />
        </div>
      </div>
      <div className="flex flex-col gap-3">
        <AnimatePresence initial={false}>
          {feed.map((c) => (
            <motion.div key={c.id} layout initial={{ opacity: 0, y: -16 }} animate={{ opacity: 1, y: 0 }}
              className={`rounded-xl border-2 px-4 py-3 font-semibold ${c.held ? "border-warn/70 bg-warn/10 text-warn" : c.ok ? "border-success/70 bg-success/10 text-success" : "border-danger/70 bg-danger/10 text-danger"}`}>
              {c.held ? "⏳ " : c.ok ? "✓ " : "✕ "}{c.text}
            </motion.div>
          ))}
        </AnimatePresence>
        {feed.length === 0 && <div className="rounded-xl border border-line p-4 text-muted">Nothing yet. Attempts show up here live.</div>}
      </div>
      <AnimatePresence>
        {held && <StepUpSheet req={held} canSign={mine} onDone={() => setHeld(null)} onError={onError} />}
      </AnimatePresence>
      <div className="sticky bottom-4 mt-4">
        {revoked ? (
          <div className="rounded-2xl border-2 border-danger py-5 text-center text-xl font-black text-danger">
            REVOKED · ₹0 can move
          </div>
        ) : (
          <SlideToRevoke disabled={!mine} onRevoke={revoke} />
        )}
      </div>
    </div>
  );
}

function SlideToRevoke({ onRevoke, disabled }: { onRevoke: () => void; disabled: boolean }) {
  const track = useRef<HTMLDivElement>(null);
  const x = useMotionValue(0);
  const [done, setDone] = useState(false);
  const fill = useTransform(x, (v) => `${v + 64}px`);
  const end = () => {
    const w = (track.current?.offsetWidth ?? 300) - 64;
    if (x.get() > w * 0.85) {
      animate(x, w, { duration: 0.1 });
      setDone(true);
      onRevoke();
    } else animate(x, 0, { type: "spring", stiffness: 400, damping: 30 });
  };
  return (
    <div ref={track} className={`relative h-16 overflow-hidden rounded-full border-2 border-danger bg-danger/10 ${disabled ? "opacity-40" : ""}`}>
      <motion.div className="absolute inset-y-0 left-0 rounded-full bg-danger/40" style={{ width: fill }} />
      <div className="absolute inset-0 flex items-center justify-center pl-12 font-bold text-danger">
        {done ? "Pulling the leash…" : "Slide to pull the leash →"}
      </div>
      <motion.div
        drag={disabled || done ? false : "x"}
        dragConstraints={track}
        dragElastic={0}
        dragMomentum={false}
        onDragEnd={end}
        style={{ x }}
        className="absolute left-0 top-0 flex h-[60px] w-[60px] cursor-grab items-center justify-center rounded-full bg-danger text-2xl text-white glow-danger"
      >
        ⛓
      </motion.div>
    </div>
  );
}

function StepUpSheet({ req, canSign, onDone, onError }: { req: HeldReq; canSign: boolean; onDone: () => void; onError: (e: string) => void }) {
  const [left, setLeft] = useState(60);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const tick = () => setLeft(Math.max(0, Math.round((Date.parse(req.expires_at) - Date.now()) / 1000)));
    tick();
    const t = setInterval(tick, 500);
    return () => clearInterval(t);
  }, [req.expires_at]);
  const answer = async (approve: boolean) => {
    setBusy(true);
    try {
      await postJSON(api.gateway(`/stepup/${req.decision_id}`), signObj({ decision_id: req.decision_id, approve, ts: new Date().toISOString().replace(/\.\d{3}Z$/, "Z") }));
      onDone();
    } catch (e) {
      onError(`Couldn't answer: ${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
  };
  const what = req.items.map((i) => `${i.brand} ${i.family}${i.qty > 1 ? ` ×${i.qty}` : ""}`).join(", ");
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-40 flex items-end bg-black/60">
      <motion.div initial={{ y: 300 }} animate={{ y: 0 }} exit={{ y: 300 }} transition={{ type: "spring", damping: 26 }}
        className="mx-auto w-full max-w-md rounded-t-3xl border-t-2 border-warn bg-surface px-6 pb-8 pt-6">
        <div className="mx-auto mb-4 h-1.5 w-12 rounded-full bg-line" />
        <h2 className="text-2xl font-bold text-white">Approve this purchase?</h2>
        <p className="mt-3 text-lg">
          Your assistant wants <b className="text-white">{what}</b> for <b className="text-white">{req.amount}</b> at {shopNameOf(req.merchant)}.
        </p>
        <p className="mt-1 text-sm text-warn">Why you&apos;re asked: {req.reason}</p>
        <div className="mt-6 flex gap-3">
          <button disabled={busy || !canSign} onClick={() => answer(true)} className="flex-1 rounded-2xl bg-accent py-4 text-lg font-black text-bg disabled:opacity-40">Approve</button>
          <button disabled={busy || !canSign} onClick={() => answer(false)} className="flex-1 rounded-2xl border-2 border-line py-4 text-lg font-bold text-white disabled:opacity-40">Deny</button>
        </div>
        <p className="mt-4 text-center text-sm text-muted">
          {canSign ? `Auto-deny in ${left}s` : "This phone didn't sign the mandate, so it can't approve."}
        </p>
      </motion.div>
    </motion.div>
  );
}
