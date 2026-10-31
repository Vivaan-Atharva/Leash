"use client";
import { motion, useReducedMotion } from "framer-motion";

/** Each digit rolls independently (400 ms), staggered right to left. */
export function Odometer({ value, className = "" }: { value: string; className?: string }) {
  const reduce = useReducedMotion();
  const chars = value.split("");
  return (
    <span className={`inline-flex tabular leading-none ${className}`} aria-label={value}>
      {chars.map((ch, i) => {
        const fromRight = chars.length - 1 - i;
        if (!/\d/.test(ch)) return <span key={`s${fromRight}`}>{ch}</span>;
        const d = Number(ch);
        return (
          <span key={`d${fromRight}`} className="relative inline-block h-[1em] overflow-hidden" style={{ width: "0.62em" }}>
            <motion.span
              className="absolute left-0 top-0 flex flex-col"
              animate={{ y: `${-d}em` }}
              transition={reduce ? { duration: 0 } : { duration: 0.4, delay: fromRight * 0.05, ease: "easeInOut" }}
            >
              {Array.from({ length: 10 }, (_, n) => (
                <span key={n} className="block h-[1em] text-center">{n}</span>
              ))}
            </motion.span>
          </span>
        );
      })}
    </span>
  );
}
