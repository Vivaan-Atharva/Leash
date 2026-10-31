"use client";
/** Proven worst case: Z3's maximum loss under each defence, with the optimal attack as witness. */
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { api, getJSON } from "@/lib/hub";
import { inr } from "@/lib/money";

type Cell = { value_paise: number | null; status: string; ms: number; witness?: { shop: string; paid_paise: number; items: { product: string; qty: number; paid_paise: number; reference_paise: number }[] }[] };
type Exposure = { ok: boolean; error?: string; ms?: number; block_paise?: number; profiles?: Record<string, Record<string, Cell>> };

const ROWS: [string, string][] = [["none", "No protection"], ["rails", "Today's rails"], ["leash", "Leash"]];
const COLS: [string, string, string][] = [
  ["total", "Total it can take", "everything that leaves the wallet"],
  ["wrong_shop", "To the wrong shop", "look-alikes, any shop not in the mandate"],
  ["off_list", "On things not on the list", "gift cards, extras, made-up items"],
  ["overpay", "Above fair price", "paid over the reference price"],
];

export function ProofOverlay({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [x, setX] = useState<Exposure | null>(null);
  useEffect(() => {
    if (!open) return;
    setX(null);
    getJSON<Exposure>(api.gateway("/mandates/current/exposure")).then(setX).catch((e) => setX({ ok: false, error: String(e) }));
  }, [open]);
  const leash = x?.profiles?.leash;
  const w = leash?.total.witness ?? [];
  return (
    <AnimatePresence>
      {open && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="absolute inset-x-0 bottom-0 top-[64px] z-40 overflow-y-auto bg-bg px-8 py-5">
          <div className="mx-auto flex max-w-[1700px] flex-col gap-4">
            <div className="flex items-baseline gap-4">
              <h2 className="text-[1.6em] font-black tracking-[0.15em] text-white">PROVEN WORST CASE</h2>
              <span className="text-muted">if the agent is completely hijacked: any orders, any shop, any items, any prices</span>
              <button onClick={onClose} className="ml-auto rounded-lg border border-line px-3 py-1 text-muted hover:text-white">Close (P)</button>
            </div>
            {!x ? (
              <div className="text-[1.2em] text-muted">Z3 is solving…</div>
            ) : !x.ok ? (
              <div className="text-danger">{x.error}</div>
            ) : (
              <>
                <table className="w-full border-separate border-spacing-2">
                  <thead>
                    <tr>
                      <th />
                      {COLS.map(([k, t, sub]) => (
                        <th key={k} className="text-left align-bottom">
                          <div className="text-[1.05em] text-white">{t}</div>
                          <div className="text-[0.75em] font-normal text-muted">{sub}</div>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {ROWS.map(([p, name], ri) => (
                      <tr key={p}>
                        <td className={`pr-4 text-[1.15em] font-black ${p === "leash" ? "text-accent" : "text-white"}`}>{name}</td>
                        {COLS.map(([k], ci) => {
                          const v = x.profiles![p][k].value_paise ?? 0;
                          const zero = v === 0;
                          return (
                            <td key={k}>
                              <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: ri * 0.35 + ci * 0.08 }}
                                className={`rounded-card border-2 px-4 py-3 ${zero ? "border-success/70 bg-success/10" : p === "leash" ? "border-line bg-surface" : "border-danger/70 bg-danger/10"}`}>
                                <div className={`tabular text-[2em] font-black ${zero ? "text-success" : p === "leash" ? "text-white" : "text-danger"}`}>{inr(v)}</div>
                                <div className="text-[0.7em] text-muted">{p === "none" ? "per reserve block" : "per week"} · proven optimal · {x.profiles![p][k].ms} ms</div>
                              </motion.div>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
                <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 1.3 }}
                  className="rounded-card border-2 border-accent/70 bg-surface p-4">
                  <div className="font-black tracking-widest text-accent">THE BEST POSSIBLE ATTACK UNDER LEASH (Z3&apos;S WITNESS)</div>
                  <div className="mt-2 flex flex-wrap gap-3">
                    {w.map((o, i) => (
                      <div key={i} className="rounded-lg border border-line px-3 py-2 text-[0.9em]">
                        <div className="font-mono text-muted">order {i + 1} · {inr(o.paid_paise)}</div>
                        {o.items.map((it, j) => <div key={j}>{it.product} ×{it.qty} <span className="text-muted">(ref {inr(it.reference_paise)})</span></div>)}
                      </div>
                    ))}
                  </div>
                  <div className="mt-3 text-[0.95em]">
                    Even a perfect attacker gets at most <b className="text-white">{inr(leash!.total.value_paise ?? 0)}</b> a week, all of it at Asha&apos;s own shops, all of it on her list,
                    and at most <b className="text-white">{inr(leash!.overpay.value_paise ?? 0)}</b> above fair price. Without Leash: <b className="text-danger">{inr(x.profiles!.none.total.value_paise ?? 0)}</b>.
                  </div>
                </motion.div>
                <div className="text-[0.72em] text-muted">
                  The mandate and each defence&apos;s checks are encoded as linear integer constraints and maximised with the Z3 SMT solver (Microsoft Research).
                  A differential test checks the formal model against the real Python checks on random requests. Solved in {x.ms} ms.
                </div>
              </>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
