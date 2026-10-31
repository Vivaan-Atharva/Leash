"use client";
import { motion } from "framer-motion";
import { useLayoutEffect, useState, type RefObject } from "react";

type Pt = { x: number; y: number };
const centre = (el: HTMLElement | null, root: HTMLElement | null): Pt | null => {
  if (!el || !root) return null;
  const r = el.getBoundingClientRect();
  const o = root.getBoundingClientRect();
  return { x: r.left - o.left + r.width / 2, y: r.top - o.top + r.height / 2 };
};

/** The signed request leaves the cart, splits in two, and flies to both lanes (600 ms). */
export function Packet({ id, root, from, left, right }: {
  id: string | null;
  root: RefObject<HTMLElement | null>;
  from: RefObject<HTMLElement | null>;
  left: RefObject<HTMLElement | null>;
  right: RefObject<HTMLElement | null>;
}) {
  const [pts, setPts] = useState<{ a: Pt; l: Pt; r: Pt } | null>(null);
  useLayoutEffect(() => {
    if (!id) return;
    const a = centre(from.current, root.current);
    const l = centre(left.current, root.current);
    const r = centre(right.current, root.current);
    setPts(a && l && r ? { a, l, r } : null);
  }, [id, root, from, left, right]);
  if (!id || !pts) return null;
  const lift = Math.min(pts.a.y, Math.min(pts.l.y, pts.r.y)) - 60;
  const fly = (to: Pt, color: string, side: string) => (
    <motion.div
      key={`${id}-${side}`}
      className="pointer-events-none absolute z-40 -ml-5 -mt-3 flex h-6 w-10 items-center justify-center rounded-md font-mono text-[11px] font-bold text-bg"
      style={{ background: color, boxShadow: `0 0 18px 4px ${color}` }}
      initial={{ x: pts.a.x, y: pts.a.y, opacity: 0, scale: 0.6 }}
      animate={{
        x: [pts.a.x, pts.a.x, (pts.a.x + to.x) / 2, to.x],
        y: [pts.a.y, pts.a.y - 30, lift, to.y],
        opacity: [0, 1, 1, 0],
        scale: [0.6, 1, 1, 0.8],
      }}
      transition={{ duration: 0.6, times: [0, 0.2, 0.55, 1], ease: "easeInOut" }}
    >
      REQ
    </motion.div>
  );
  return (
    <>
      {fly(pts.l, "#FF5C7A", "l")}
      {fly(pts.r, "#2ECDDB", "r")}
    </>
  );
}
