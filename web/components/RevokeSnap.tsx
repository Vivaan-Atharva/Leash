"use client";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";

/** Chain-snap across the right lane when Asha revokes (500 ms), then a REVOKED flash. */
export function RevokeSnap({ seq, time }: { seq: number | null; time: string | null }) {
  const [show, setShow] = useState(false);
  useEffect(() => {
    if (!seq) return;
    setShow(true);
    const t = setTimeout(() => setShow(false), 2600);
    return () => clearTimeout(t);
  }, [seq]);
  const links = Array.from({ length: 8 });
  return (
    <AnimatePresence>
      {show && (
        <motion.div key={seq} className="pointer-events-none absolute inset-0 z-30 flex flex-col items-center justify-center bg-bg/40"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <div className="flex items-center">
            {links.map((_, i) => {
              const leftSide = i < links.length / 2;
              return (
                <motion.svg key={i} width="54" height="30" viewBox="0 0 54 30" className="-mx-1"
                  initial={{ x: 0, rotate: 0, opacity: 1 }}
                  animate={{ x: leftSide ? -40 - (3 - i) * 8 : 40 + (i - 4) * 8, rotate: leftSide ? -18 : 18, opacity: [1, 1, 0.3] }}
                  transition={{ delay: 0.15, duration: 0.5, ease: "easeOut" }}>
                  <rect x="3" y="5" width="48" height="20" rx="10" fill="none" stroke="#FF5C7A" strokeWidth="5" />
                </motion.svg>
              );
            })}
          </div>
          <motion.div initial={{ scale: 1.5, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ delay: 0.45, type: "spring" }}
            className="mt-6 rounded-xl border-4 border-danger bg-bg px-6 py-2 text-[1.6em] font-black text-danger glow-danger">
            LEASH PULLED{time ? ` · ${time}` : ""}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
