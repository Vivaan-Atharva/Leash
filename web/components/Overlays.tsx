"use client";
import { AnimatePresence, motion } from "framer-motion";
import { inr } from "@/lib/money";
import type { Director } from "@/lib/useLeash";

export function DirectorBanner({ director, revoked }: { director: Director; revoked: boolean }) {
  const show =
    (director.moment === "REVOKE" && !revoked) || director.status === "waiting_for_revoke";
  return (
    <AnimatePresence>
      {show && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
          className="absolute bottom-24 left-1/2 z-30 -translate-x-1/2 rounded-2xl border-2 border-danger bg-bg/95 px-8 py-4 text-center glow-danger">
          <div className="text-[1.5em] font-black text-white">Asha pulls the leash</div>
          <div className="text-danger">{director.status === "waiting_for_revoke" ? "Revoke on the phone first, then press →" : "Slide to revoke on the phone"}</div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function Totals({ open, left, right, onClose }: { open: boolean; left: number; right: number; onClose: () => void }) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div onClick={onClose} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="absolute inset-0 z-50 flex flex-col items-center justify-center gap-10 bg-bg/95">
          <div className="flex gap-20">
            <div className="text-center">
              <div className="text-[1.4em] font-black tracking-[0.2em] text-danger">NO LEASH LOST</div>
              <motion.div initial={{ scale: 0.6 }} animate={{ scale: 1 }} className="tabular text-[7em] font-black text-danger text-glow-danger">{inr(left)}</motion.div>
            </div>
            <div className="text-center">
              <div className="text-[1.4em] font-black tracking-[0.2em] text-success">WITH LEASH LOST</div>
              <motion.div initial={{ scale: 0.6 }} animate={{ scale: 1 }} transition={{ delay: 0.25 }} className="tabular text-[7em] font-black text-success text-glow-success">{inr(right)}</motion.div>
            </div>
          </div>
          <div className="text-[1.6em] text-white">Leash doesn&apos;t make the AI smarter. It makes the payment path stricter.</div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function ReportOverlay({ id, onClose }: { id: string | null; onClose: () => void }) {
  return (
    <AnimatePresence>
      {id && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="absolute inset-0 z-50 flex flex-col bg-bg/95 p-6">
          <div className="mb-2 flex justify-end">
            <button onClick={onClose} className="rounded-lg border border-line px-4 py-1 text-muted hover:text-white">Close (Esc)</button>
          </div>
          <iframe src={`/report/${id}?embed=1`} title="Dispute report" className="min-h-0 flex-1 rounded-card border border-line bg-bg" />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
