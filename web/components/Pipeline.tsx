"use client";
import { AnimatePresence, motion } from "framer-motion";
import type { Check, Decision } from "@/lib/useLeash";
import { inr } from "@/lib/money";

export const CHECK_LABEL: Record<string, string> = {
  identity: "Identity",
  merchant: "Right shop",
  limits: "Spending limits",
  intent: "On the list",
  price: "Fair price",
  validity: "Still valid",
};
const ORDER = ["identity", "merchant", "limits", "intent", "price", "validity"];
export const PACKET_MS = 550; // nodes start lighting once the packet reaches the gateway
const STAGGER = 0.12;

function Node({ n, name, check, decisionId, pending }: { n: number; name: string; check?: Check; decisionId?: string; pending: boolean }) {
  const delay = PACKET_MS / 1000 + (n - 1) * STAGGER;
  const state = !decisionId ? (pending ? "pending" : "idle") : !check ? "skipped" : check.pass ? "pass" : "fail";
  const ring =
    state === "pass" ? "border-success bg-success/15 text-success" :
    state === "fail" ? "border-danger bg-danger/20 text-danger glow-danger" :
    state === "skipped" ? "border-line/50 text-muted/50" :
    state === "pending" ? "border-accent text-accent" : "border-line text-muted";
  return (
    <motion.div
      key={`${decisionId ?? "none"}-${n}`}
      className={`flex items-center gap-3 rounded-[10px] border px-3 py-[0.32em] short:py-[0.12em] ${ring}`}
      initial={decisionId ? { borderColor: "#2ECDDB", backgroundColor: "rgba(46,205,219,0.12)", x: 0 } : false}
      animate={
        state === "fail"
          ? { borderColor: "#FF5C7A", backgroundColor: "rgba(255,92,122,0.2)", x: [0, -6, 6, -3, 0] }
          : state === "pass"
            ? { borderColor: "#34D399", backgroundColor: "rgba(52,211,153,0.12)" }
            : state === "pending"
              ? { opacity: [0.5, 1, 0.5] }
              : {}
      }
      transition={state === "pending" ? { duration: 1, repeat: Infinity } : { delay, duration: state === "fail" ? 0.3 : 0.15 }}
    >
      <span className="flex h-[1.6em] w-[1.6em] shrink-0 items-center justify-center rounded-full border border-current font-mono text-[0.8em]">{n}</span>
      <span className="flex-1 font-medium">{CHECK_LABEL[name]}</span>
      <motion.span
        key={`${decisionId}-${n}-mark`}
        initial={{ opacity: 0, scale: 0.4 }}
        animate={{ opacity: decisionId ? 1 : 0, scale: 1 }}
        transition={{ delay: delay + 0.05, duration: 0.15 }}
        className="text-[1.2em] font-bold"
      >
        {state === "pass" ? "✓" : state === "fail" ? "✕" : state === "skipped" ? "–" : ""}
      </motion.span>
    </motion.div>
  );
}

export function Stamp({ decision }: { decision: Decision }) {
  const delay = PACKET_MS / 1000 + ORDER.length * STAGGER + 0.05;
  const blocked = decision.outcome !== "ALLOWED";
  const held = decision.outcome === "HELD";
  return (
    <motion.div
      key={decision.decision_id}
      initial={{ opacity: 0, scale: 1.4, rotate: 0 }}
      animate={{ opacity: 1, scale: 1, rotate: blocked ? -8 : -3 }}
      transition={{ delay, type: "spring", stiffness: 420, damping: 18 }}
      className={`mx-auto mt-4 short:mt-2 w-fit rounded-xl border-4 px-5 py-1.5 text-center font-black tracking-wide ${
        held ? "border-warn text-warn" : blocked ? "border-danger text-danger text-glow-danger glow-danger" : "border-success text-success text-glow-success glow-success"
      }`}
    >
      <div className="text-[1.4em] leading-tight short:text-[1.1em]">
        {held ? "HELD · APPROVE ON PHONE" : blocked ? "BLOCKED · ₹0 MOVED" : `ALLOWED · ${inr(decision.amount_paise)}`}
      </div>
    </motion.div>
  );
}

export function Pipeline({ decision, pending }: { decision: Decision | null; pending: boolean }) {
  const checks = new Map((decision?.checks ?? []).map((c) => [c.name, c]));
  const firstFail = decision?.checks.find((c) => !c.pass);
  return (
    <div className="rounded-card border border-line bg-surface p-4 short:p-2.5">
      <div className="mb-3 short:mb-1.5 flex items-baseline justify-between">
        <span className="font-bold tracking-widest text-accent">LEASH GATEWAY</span>
        <span className="font-mono text-[0.75em] text-muted">6 checks · no LLM</span>
      </div>
      <div className="flex flex-col gap-2 short:gap-1">
        {ORDER.map((name, i) => (
          <Node key={name} n={i + 1} name={name} check={checks.get(name)} decisionId={decision?.decision_id} pending={pending} />
        ))}
      </div>
      <AnimatePresence mode="wait">
        {decision && (
          <motion.div key={decision.decision_id} initial={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <Stamp decision={decision} />
            <motion.div
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: PACKET_MS / 1000 + 0.9 }}
              className="mt-5 short:mt-2 text-center"
            >
              {firstFail && (
                <div className="text-[0.85em] leading-snug text-body">
                  <span className="font-semibold text-danger">Check {firstFail.n} · {CHECK_LABEL[firstFail.name]}:</span> {firstFail.detail}
                  {decision.checks.filter((c) => !c.pass).length > 1 && (
                    <span className="text-muted"> (+{decision.checks.filter((c) => !c.pass).length - 1} more)</span>
                  )}
                </div>
              )}
              <div className="mt-1 font-mono text-[0.8em] text-muted">
                decided in <span className="text-accent">{(decision.decided_in_us / 1000).toFixed(1)} ms</span>
                {decision.log_index ? <> · log #{decision.log_index}</> : null}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
