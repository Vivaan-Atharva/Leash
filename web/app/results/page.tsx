"use client";

import { motion } from "framer-motion";
import { useCallback, useEffect, useRef, useState } from "react";
import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, getJSON, hubWsUrl, postJSON, type LeashEvent } from "@/lib/hub";
import { inr } from "@/lib/money";

const LABEL: Record<string, string> = {
  agent_alone: "Agent alone",
  hardened_prompt: "Hardened prompt",
  rails: "Today's rails",
  leash: "Leash",
};
const ALL = ["agent_alone", "hardened_prompt", "rails", "leash"];

type Cell = { runs: number; mean_lost_paise: number; lost_runs: number; honest_ok_runs: number; failing: string[] };
type Row = { case_id: string; name: string; kind: string; in_scope: boolean; technique: string; cells: Record<string, Cell> };
type Summary = {
  available: boolean; mode?: string; model?: string; runs?: number; generated_at?: string; running?: boolean;
  defences?: string[]; lost_paise?: Record<string, number>; honest_total?: number; honest_allowed?: Record<string, number>;
  attack_total?: number; matrix?: Row[];
};

function CellView({ row, cell, delay }: { row: Row; cell?: Cell; delay: number }) {
  if (!cell) return <td className="px-2 py-1.5 text-center text-muted/50">needs LLM</td>;
  const attack = row.kind === "attack";
  const bad = attack ? cell.mean_lost_paise > 0 : cell.honest_ok_runs < cell.runs;
  const text = attack
    ? bad ? `${inr(cell.mean_lost_paise)}${cell.lost_runs < cell.runs ? ` · ${cell.lost_runs}/${cell.runs}` : ""}` : "✓"
    : bad ? `✕ ${cell.honest_ok_runs}/${cell.runs}` : "✓ allowed";
  const why = attack && !bad ? `blocked · checks ${[...new Set(cell.failing.join(" ").split(/[ ,]/).filter((x) => x && x !== "-"))].join(", ") || "–"}` : undefined;
  return (
    <td className="px-2 py-1">
      <motion.div
        initial={{ opacity: 0, scale: 0.85 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay, duration: 0.18 }}
        title={why}
        className={`rounded-md border px-2 py-0.5 text-center font-mono font-bold ${
          bad ? "border-danger/70 bg-danger/15 text-danger" : "border-success/60 bg-success/10 text-success"}`}
      >
        {text}
      </motion.div>
    </td>
  );
}

export default function Results() {
  const [s, setS] = useState<Summary | null>(null);
  const [replayKey, setReplayKey] = useState(0);
  const [msg, setMsg] = useState<string | null>(null);
  const [fromControl, setFromControl] = useState(false);
  const pending = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(() => getJSON<Summary>(api.hub("/eval/results")).then(setS).catch(() => setS({ available: false })), []);

  useEffect(() => {
    setFromControl(new URLSearchParams(window.location.search).has("from"));
    load();
    const ws = new WebSocket(hubWsUrl());
    ws.onmessage = (m) => {
      const e = JSON.parse(m.data) as LeashEvent;
      if (e.backfill) return;
      if (e.type === "eval.row" || e.type === "eval.status") {
        if (e.type === "eval.status") setMsg(e.data.status === "done" ? "Suite finished" : `Running ${e.data.total} runs (${e.data.mode})…`);
        if (pending.current) return;
        pending.current = setTimeout(() => {
          pending.current = null;
          load();
        }, 400);
      }
    };
    const onKey = (k: KeyboardEvent) => {
      if (k.key === "Escape" || k.key === "ArrowLeft") window.location.href = "/control";
      if (k.key === "f" || k.key === "F") document.documentElement.requestFullscreen().catch(() => {});
    };
    window.addEventListener("keydown", onKey);
    return () => {
      ws.close();
      window.removeEventListener("keydown", onKey);
    };
  }, [load]);

  const runLive = async () => {
    const r = await postJSON(api.hub("/eval/run"), { runs: 3 }).catch((e) => ({ ok: false, error: String(e) }));
    setMsg(r.ok ? "Suite started. Cells fill in as runs finish." : r.busy ? "Something is already running" : r.error);
  };

  const defs = ALL;
  const mx = s?.matrix ?? [];
  const attacks = mx.filter((r) => r.kind === "attack");
  const honest = mx.filter((r) => r.kind === "honest");
  const chart = (s?.defences ?? []).map((d) => ({ d, name: LABEL[d], lost: (s?.lost_paise?.[d] ?? 0) / 100 }));
  const badge = s?.mode === "live" ? `LIVE · ${s.model}` : "SCRIPTED (no LLM)";

  return (
    <main className="mx-auto flex min-h-screen max-w-[1800px] flex-col gap-6 px-8 py-8 text-[clamp(14px,0.9vw,19px)]">
      <header className="flex flex-wrap items-end gap-4">
        <div>
          <div className="text-sm font-bold tracking-[0.3em] text-accent">LEASH · ATTACK SUITE</div>
          <h1 className="text-[2.6em] font-black text-white">Measured, not claimed</h1>
        </div>
        {s?.available && (
          <span className="mb-2 flex gap-2">
            <span className="rounded-full border-2 border-warn px-3 py-0.5 font-mono font-bold text-warn">{s.running ? "RUNNING" : "CACHED"}</span>
            <span className="rounded-full border-2 border-line px-3 py-0.5 font-mono text-muted">{badge} · {s.runs} runs each</span>
          </span>
        )}
        <div className="mb-2 ml-auto flex gap-3">
          <button onClick={() => setReplayKey((k) => k + 1)} className="rounded-lg border border-line px-4 py-2 text-muted hover:text-white">Replay fill</button>
          <button onClick={runLive} className="rounded-lg bg-accent px-4 py-2 font-bold text-bg">Run suite</button>
          {fromControl && <a href="/control" className="rounded-lg border border-line px-4 py-2 text-muted hover:text-white">← Mission Control</a>}
        </div>
      </header>
      {msg && <div className="rounded-lg border border-line bg-surface px-4 py-2">{msg}</div>}

      {!s ? (
        <div className="text-muted">Loading…</div>
      ) : !s.available ? (
        <div className="rounded-card border border-line bg-surface p-8 text-lg">
          No results yet. Start the services and press <b>Run suite</b>, or run <code className="font-mono">make eval</code>.
        </div>
      ) : (
        <>
          <section className="grid grid-cols-2 gap-4 lg:grid-cols-5">
            {defs.map((d) => {
              const has = s.defences?.includes(d);
              const v = s.lost_paise?.[d] ?? 0;
              const leash = d === "leash";
              return (
                <div key={d} className={`rounded-card border-2 p-4 ${leash ? "border-accent glow-accent" : "border-line"} bg-surface`}>
                  <div className="text-[0.8em] font-bold uppercase tracking-widest text-muted">{LABEL[d]}</div>
                  <div className="mt-1 text-[0.75em] text-muted">₹ lost to {s.attack_total} attacks</div>
                  <div className={`tabular text-[2.6em] font-black ${!has ? "text-muted/50" : v > 0 ? (leash ? "text-white" : "text-danger") : "text-success"}`}>
                    {has ? inr(v) : "–"}
                  </div>
                  {!has && <div className="text-[0.75em] text-muted">needs a LIVE LLM run</div>}
                </div>
              );
            })}
            <div className="rounded-card border-2 border-success/70 bg-success/10 p-4">
              <div className="text-[0.8em] font-bold uppercase tracking-widest text-success">Honest purchases allowed</div>
              <div className="mt-1 text-[0.75em] text-muted">by Leash</div>
              <div className="tabular text-[2.6em] font-black text-success">
                {s.honest_allowed?.leash ?? 0}/{s.honest_total}
              </div>
            </div>
          </section>

          <section className="grid gap-6 xl:grid-cols-[1.6fr_1fr]">
            <div className="overflow-x-auto rounded-card border border-line bg-surface p-4" key={replayKey}>
              <table className="w-full border-separate border-spacing-0">
                <thead>
                  <tr className="text-left text-[0.8em] uppercase tracking-widest text-muted">
                    <th className="px-2 pb-2">Attack</th>
                    {defs.map((d) => <th key={d} className={`px-2 pb-2 text-center ${d === "leash" ? "text-accent" : ""}`}>{LABEL[d]}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {attacks.map((r, i) => (
                    <tr key={r.case_id} className="border-t border-line/40">
                      <td className="px-2 py-1">
                        <span className="font-mono text-muted">{r.case_id}</span> <span className="text-white">{r.name}</span>
                        {r.in_scope && <span className="ml-2 rounded-full border border-warn/70 px-2 text-[0.7em] text-warn">in scope</span>}
                        <div className="text-[0.75em] text-muted">{r.technique}</div>
                      </td>
                      {defs.map((d, j) => <CellView key={d} row={r} cell={r.cells[d]} delay={i * 0.06 + j * 0.03} />)}
                    </tr>
                  ))}
                  <tr><td colSpan={5} className="px-2 pb-1 pt-4 text-[0.8em] uppercase tracking-widest text-muted">Honest purchases</td></tr>
                  {honest.map((r, i) => (
                    <tr key={r.case_id}>
                      <td className="px-2 py-1"><span className="font-mono text-muted">{r.case_id}</span> <span className="text-white">{r.name}</span></td>
                      {defs.map((d, j) => <CellView key={d} row={r} cell={r.cells[d]} delay={(attacks.length + i) * 0.06 + j * 0.03} />)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex flex-col self-start rounded-card border border-line bg-surface p-4 xl:sticky xl:top-6">
              <h2 className="text-[1.1em] font-bold text-white">₹ lost to attacks, by defence</h2>
              <div className="text-[0.8em] text-muted">mean per run, summed over {s.attack_total} attacks</div>
              <div className="h-[min(52vh,440px)]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chart} margin={{ top: 36, right: 8, left: 8, bottom: 8 }}>
                    <XAxis dataKey="name" tick={{ fill: "#CBD5E1", fontSize: 15 }} axisLine={{ stroke: "#4B3EA6" }} tickLine={false} />
                    <YAxis hide />
                    <Tooltip
                      cursor={{ fill: "rgba(75,62,166,0.25)" }}
                      contentStyle={{ background: "#1B1249", border: "1px solid #4B3EA6", borderRadius: 8, color: "#fff" }}
                      formatter={(v: number) => [inr(Math.round(v * 100)), "lost"]}
                    />
                    <Bar dataKey="lost" radius={[4, 4, 0, 0]} maxBarSize={110} isAnimationActive animationDuration={800} key={replayKey}>
                      {chart.map((c) => <Cell key={c.d} fill={c.d === "leash" ? "#2ECDDB" : "#FF5C7A"} />)}
                      <LabelList dataKey="lost" position="top" formatter={(v: number) => inr(Math.round(v * 100))}
                        style={{ fill: "#FFFFFF", fontSize: 18, fontWeight: 800 }} />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-2 text-[0.8em] leading-snug text-muted">
                What Leash still lets through is inside the mandate: order splitting under the weekly cap and a duplicate order.
                The mandate allows these, so they are the stated limits.
              </p>
            </div>
          </section>
          <footer className="text-[0.8em] text-muted">
            Ground truth per case is in eval/attacks.json and eval/honest.json. Results in eval/results.csv, generated {s.generated_at}.
          </footer>
        </>
      )}
    </main>
  );
}
