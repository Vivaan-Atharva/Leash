"use client";
import { motion } from "framer-motion";
import type { ChainEntry } from "@/lib/useLeash";

export function ChainBar({ chain, verify, tampered, onVerify, onTamper, flash }: {
  chain: ChainEntry[];
  verify: { ok: boolean; broken_at: number | null; length: number } | null;
  tampered: boolean;
  onVerify: () => void;
  onTamper: () => void;
  flash: number;
}) {
  const shown = chain.slice(-9);
  const broken = verify && !verify.ok ? verify.broken_at : null;
  return (
    <div className="relative flex items-center gap-4 border-t border-line bg-surface px-6 py-3">
      <span className="shrink-0 font-bold tracking-widest text-muted">AUDIT CHAIN</span>
      <div className="flex min-w-0 flex-1 items-center gap-1 overflow-hidden">
        {shown.length === 0 && <span className="text-muted">empty</span>}
        {shown.map((c, i) => {
          const bad = broken !== null && c.index >= broken;
          return (
            <div key={c.index} className="flex items-center gap-1">
              {i > 0 && <span className={bad ? "text-danger" : "text-line"}>→</span>}
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{
                  opacity: 1, y: 0,
                  borderColor: bad ? "#FF5C7A" : "#4B3EA6",
                  backgroundColor: bad ? "rgba(255,92,122,0.18)" : "rgba(46,34,119,1)",
                }}
                transition={{ delay: bad ? (c.index - (broken ?? 0)) * 0.06 : 0, duration: 0.2 }}
                className="rounded-md border px-2 py-1 font-mono text-[0.72em] leading-tight"
                title={`${c.type} ${c.hash}`}
              >
                <span className={bad ? "text-danger" : "text-white"}>#{c.index}</span>{" "}
                <span className="text-muted">{c.hash.slice(0, 4)}…</span>
                <div className={`text-[0.85em] ${bad ? "text-danger" : "text-muted/80"}`}>{c.type.replace("_", " ").toLowerCase()}</div>
              </motion.div>
            </div>
          );
        })}
      </div>
      <motion.button
        key={flash}
        onClick={onVerify}
        animate={flash ? { scale: [1, 1.12, 1] } : {}}
        className={`shrink-0 rounded-lg border px-4 py-2 font-mono font-bold ${
          verify?.ok === false ? "border-danger text-danger" : "border-success text-success"
        }`}
      >
        VERIFY {verify?.ok === false ? "✕" : "✓"}
      </motion.button>
      <button onClick={onTamper} className={`shrink-0 rounded-lg border px-4 py-2 font-mono font-bold ${tampered ? "border-accent text-accent" : "border-line text-muted hover:text-white"}`}>
        {tampered ? "RESTORE" : "TAMPER"}
      </button>
      {broken !== null && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="absolute -top-14 left-1/2 -translate-x-1/2 rounded-xl border-2 border-danger bg-bg px-6 py-2 text-[1.1em] font-bold text-danger glow-danger"
        >
          Log tampered at #{broken}. Chain broken.
        </motion.div>
      )}
    </div>
  );
}
