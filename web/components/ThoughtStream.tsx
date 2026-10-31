"use client";
import { useEffect, useRef, useState } from "react";
import type { Line } from "@/lib/useLeash";

function Typed({ text, animate }: { text: string; animate: boolean }) {
  const [n, setN] = useState(animate ? 0 : text.length);
  useEffect(() => {
    if (!animate) return;
    const per = Math.max(8, Math.min(28, 1200 / text.length));
    const t = setInterval(() => setN((k) => (k >= text.length ? (clearInterval(t), k) : k + 1)), per);
    return () => clearInterval(t);
  }, [text, animate]);
  return (
    <>
      {text.slice(0, n)}
      {n < text.length && <span className="animate-pulse text-accent">▍</span>}
    </>
  );
}

const style: Record<Line["kind"], string> = {
  thought: "text-white",
  tool: "text-accent",
  result: "text-muted",
  system: "text-warn",
};

export function ThoughtStream({ lines }: { lines: Line[] }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [lines]);
  const lastThought = [...lines].reverse().find((l) => l.kind === "thought")?.id;
  return (
    <div className="min-h-0 flex-1 overflow-y-auto rounded-card border border-line bg-surface px-4 py-3 font-mono text-[0.8em] leading-relaxed">
      {lines.length === 0 && <div className="text-muted">Waiting for the agent…</div>}
      {lines.map((l) => (
        <div key={l.id} className={`${style[l.kind]} ${l.kind === "tool" ? "pl-4" : ""}`}>
          {l.kind === "thought" && <span className="text-muted">› </span>}
          {l.kind === "tool" && <span className="text-muted">⚙ </span>}
          <Typed text={l.text} animate={l.kind === "thought" && l.id === lastThought} />
        </div>
      ))}
      <div ref={end} />
    </div>
  );
}
