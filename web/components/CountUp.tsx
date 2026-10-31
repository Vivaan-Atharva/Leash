"use client";
import { useEffect, useRef, useState } from "react";
import { inr } from "@/lib/money";

/** Counts to the new paise value over 800 ms. */
export function CountUp({ paise, className = "" }: { paise: number; className?: string }) {
  const [shown, setShown] = useState(paise);
  const from = useRef(paise);
  useEffect(() => {
    const start = performance.now();
    const a = from.current;
    let raf = 0;
    const tick = (t: number) => {
      const k = Math.min(1, (t - start) / 800);
      const eased = 1 - Math.pow(1 - k, 3);
      setShown(Math.round(a + (paise - a) * eased));
      if (k < 1) raf = requestAnimationFrame(tick);
      else from.current = paise;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [paise]);
  return <span className={`tabular ${className}`}>{inr(Math.round(shown / 100) * 100)}</span>;
}
