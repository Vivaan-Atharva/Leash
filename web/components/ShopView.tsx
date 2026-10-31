"use client";
import { useEffect, useRef, useState } from "react";
import { applyXray } from "./xray";

const PAGE_W = 1100; // shop pages are laid out for desktop; scale them into the column

export function ShopView({ url, merchant, injections, xray, onToggle, onTrace }: {
  url: string | null;
  merchant?: string;
  injections: { style: string; label: string }[];
  xray: boolean;
  onToggle: () => void;
  onTrace?: () => void;
}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0.6);
  const [height, setHeight] = useState(400);

  useEffect(() => {
    if (!box.current) return;
    const ro = new ResizeObserver(([e]) => {
      setScale(e.contentRect.width / PAGE_W);
      setHeight(e.contentRect.height);
    });
    ro.observe(box.current);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    applyXray(frame.current?.contentDocument, xray);
  }, [xray, url]);

  return (
    <div className="flex min-h-0 flex-1 flex-col rounded-card border border-line bg-surface">
      <div className="flex items-center gap-3 border-b border-line px-4 py-2">
        <span className="font-semibold text-white">Shop view</span>
        <span className="truncate font-mono text-[0.75em] text-muted">{merchant ? `${merchant}${url?.replace(/^\/shop\/[^/]+/, "").replace("?view=1", "")}` : "—"}</span>
        {injections.length > 0 && !xray && (
          <span className="rounded-full border border-danger/60 px-2 text-[0.7em] text-danger">{injections.length} hidden</span>
        )}
        {onTrace && (
          <button onClick={onTrace} className="ml-auto rounded-full border border-line px-3 py-0.5 font-mono text-[0.75em] font-bold tracking-wider text-muted hover:text-white">
            TRACE (A)
          </button>
        )}
        <button
          onClick={onToggle}
          className={`${onTrace ? "" : "ml-auto "} rounded-full border px-3 py-0.5 font-mono text-[0.75em] font-bold tracking-wider transition ${
            xray ? "border-danger bg-danger text-white glow-danger" : "border-line text-muted hover:text-white"
          }`}
        >
          X-RAY: {xray ? "ON" : "OFF"}
        </button>
      </div>
      <div ref={box} className="relative min-h-0 flex-1 overflow-hidden rounded-b-card bg-white">
        {url ? (
          <iframe
            ref={frame}
            key={url}
            src={url}
            title="shop"
            onLoad={() => applyXray(frame.current?.contentDocument, xray)}
            className="absolute left-0 top-0 origin-top-left border-0"
            style={{ width: PAGE_W, height: height / scale, transform: `scale(${scale})` }}
          />
        ) : (
          <div className="flex h-full items-center justify-center bg-surface-2 text-muted">The agent hasn&apos;t opened a page yet</div>
        )}
      </div>
    </div>
  );
}
