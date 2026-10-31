"use client";
import { AnimatePresence, motion } from "framer-motion";
import type { Decision, Payment } from "@/lib/useLeash";
import { inr } from "@/lib/money";
import { CountUp } from "./CountUp";
import { Odometer } from "./Odometer";
import { PACKET_MS, Pipeline } from "./Pipeline";
import { useDelayed } from "./useDelayed";

function Wallet({ balance, tone }: { balance: number | null; tone: "left" | "right" }) {
  const shown = useDelayed(balance, PACKET_MS);
  return (
    <div className="rounded-card border border-line bg-surface px-4 py-3 short:py-1.5">
      <div className="text-[0.8em] font-semibold tracking-widest text-muted">
        WALLET {tone === "left" ? "L" : "R"} · {tone === "left" ? "any agent-signed debit" : "gateway-signed debits only"}
      </div>
      <div className="mt-1 text-[3.1em] font-bold text-white short:text-[2.3em]">
        {shown === null ? "—" : <Odometer value={inr(shown)} />}
      </div>
    </div>
  );
}

function Lost({ paise, tone }: { paise: number; tone: "left" | "right" }) {
  const shown = useDelayed(paise, PACKET_MS);
  const bad = tone === "left";
  return (
    <div className={`shrink-0 rounded-card border-2 px-4 py-3 short:py-1.5 ${bad ? "border-danger/70 bg-danger/10" : "border-success/70 bg-success/10"}`}>
      <div className={`text-[0.85em] font-bold tracking-widest ${bad ? "text-danger" : "text-success"}`}>LOST SO FAR</div>
      <CountUp paise={shown} className={`block text-[3em] font-black leading-tight short:text-[2.2em] ${bad ? "text-danger text-glow-danger" : "text-success text-glow-success"}`} />
    </div>
  );
}

export function LeftLane({ balance, payments, lost, targetRef }: {
  balance: number | null; payments: Payment[]; lost: number; targetRef: React.RefObject<HTMLDivElement | null>;
}) {
  const shown = useDelayed(payments, PACKET_MS);
  return (
    <section className="flex min-h-0 flex-col gap-4 short:gap-2">
      <h2 className="text-[1.3em] font-black tracking-[0.2em] text-danger">NO LEASH</h2>
      <div ref={targetRef}><Wallet balance={balance} tone="left" /></div>
      <div className="min-h-0 flex-1 overflow-hidden rounded-card border border-line bg-surface p-4">
        <div className="mb-2 text-[0.8em] font-semibold tracking-widest text-muted">PAYMENTS (agent key goes straight to the rail)</div>
        <AnimatePresence initial={false}>
          {shown.map((p, i) => (
            <motion.div key={p.id} layout initial={{ opacity: 0, x: -30 }} animate={{ opacity: 1, x: 0 }}
              className={`mb-2 flex items-center justify-between rounded-lg border px-3 py-2 ${i === 0 ? "border-danger bg-danger/15" : "border-line/60 opacity-70"}`}>
              <span className="font-bold text-danger">✕ {inr(p.amount_paise)} PAID</span>
              <span className="font-mono text-[0.8em] text-muted">{p.merchant}</span>
            </motion.div>
          ))}
        </AnimatePresence>
        {shown.length === 0 && <div className="text-muted">No payments yet</div>}
      </div>
      <Lost paise={lost} tone="left" />
    </section>
  );
}

export function RightLane({ balance, decision, pending, lost, targetRef, onOpen }: {
  balance: number | null; decision: Decision | null; pending: boolean; lost: number; targetRef: React.RefObject<HTMLDivElement | null>;
  onOpen?: (id: string) => void;
}) {
  return (
    <section className="flex min-h-0 flex-1 flex-col gap-4 short:gap-2">
      <h2 className="text-[1.3em] font-black tracking-[0.2em] text-success">WITH LEASH</h2>
      <Wallet balance={balance} tone="right" />
      <div ref={targetRef} className="min-h-0 flex-1 overflow-hidden"><Pipeline decision={decision} pending={pending} onOpen={onOpen} /></div>
      <Lost paise={lost} tone="right" />
    </section>
  );
}
