"use client";

// Phase 1: minimal Mission Control. A raw, live list of hub events to prove the pipe works.
// Phase 2 replaces this with the Stitch design.
import { useEffect, useRef, useState } from "react";
import { hubBase, hubWsUrl, type LeashEvent } from "@/lib/hub";

const laneColor: Record<string, string> = {
  left: "text-rose-400",
  right: "text-emerald-400",
  both: "text-cyan-300",
  system: "text-amber-300",
};

export default function Control() {
  const [events, setEvents] = useState<LeashEvent[]>([]);
  const [status, setStatus] = useState<"connecting" | "open" | "closed">("connecting");
  const retry = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let stopped = false;
    const connect = () => {
      setStatus("connecting");
      ws = new WebSocket(hubWsUrl());
      ws.onopen = () => setStatus("open");
      ws.onmessage = (m) => {
        const ev = JSON.parse(m.data) as LeashEvent;
        if (ev.type === "system.mode" && (ev.data as { reset?: boolean }).reset) {
          setEvents([ev]);
          return;
        }
        setEvents((prev) => (prev.some((p) => p.seq === ev.seq) ? prev : [ev, ...prev].slice(0, 500)));
      };
      ws.onclose = () => {
        setStatus("closed");
        if (!stopped) retry.current = setTimeout(connect, 1000);
      };
    };
    connect();
    const ping = setInterval(() => ws?.readyState === 1 && ws.send("ping"), 15000);
    return () => {
      stopped = true;
      clearInterval(ping);
      if (retry.current) clearTimeout(retry.current);
      ws?.close();
    };
  }, []);

  const reset = () => fetch(`${hubBase()}/demo/reset`, { method: "POST" });

  return (
    <main className="min-h-screen bg-[#1B1249] p-6 font-mono text-[#CBD5E1]">
      <header className="mb-4 flex items-center gap-4">
        <h1 className="text-2xl font-bold text-white">LEASH · events</h1>
        <span className={status === "open" ? "text-emerald-400" : "text-rose-400"}>● {status}</span>
        <span className="text-[#AC99CF]">{events.length} events</span>
        <button onClick={reset} className="ml-auto rounded border border-[#4B3EA6] px-3 py-1 hover:bg-[#251A63]">
          Reset demo
        </button>
      </header>
      <ul className="space-y-1 text-sm">
        {events.map((e) => (
          <li key={e.seq} className="flex gap-3 border-b border-[#251A63] py-1">
            <span className="w-12 text-right text-[#AC99CF]">#{e.seq}</span>
            <span className={`w-16 ${laneColor[e.lane] ?? ""}`}>{e.lane}</span>
            <span className="w-44 text-white">{e.type}</span>
            <span className="truncate">{JSON.stringify(e.data)}</span>
          </li>
        ))}
      </ul>
    </main>
  );
}
