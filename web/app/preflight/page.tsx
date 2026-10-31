"use client";

import { useCallback, useEffect, useState } from "react";
import { api, getJSON, postJSON } from "@/lib/hub";

type Item = { name: string; ok: boolean; detail: string; required: boolean };
const MANUAL = ["Screen sleep disabled", "Notifications off (Do Not Disturb)", "Browser zoom 100%, clean profile", "Ran one full director run in REPLAY", "Pressed R right before going on"];

export default function Preflight() {
  const [items, setItems] = useState<Item[] | null>(null);
  const [ok, setOk] = useState<boolean | null>(null);
  const [checked, setChecked] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    try {
      const r = await getJSON(api.hub("/preflight"));
      setItems(r.items);
      setOk(r.ok);
    } catch {
      setItems([{ name: "hub", ok: false, detail: "not reachable: run make demo", required: true }]);
      setOk(false);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [load]);

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-6 py-10">
      <div className="flex items-center gap-4">
        <h1 className="text-4xl font-black text-white">Preflight</h1>
        {ok !== null && (
          <span className={`rounded-full border-2 px-4 py-1 font-bold ${ok ? "border-success text-success" : "border-danger text-danger"}`}>
            {ok ? "READY" : "NOT READY"}
          </span>
        )}
        <button onClick={() => postJSON(api.hub("/demo/reset")).then(load)} className="ml-auto rounded-lg border border-line px-4 py-2 text-muted hover:text-white">Reset demo</button>
        <a href="/control" className="rounded-lg bg-accent px-4 py-2 font-bold text-bg">Mission Control →</a>
      </div>
      <ul className="flex flex-col gap-2">
        {(items ?? []).map((i) => (
          <li key={i.name} className="flex items-center gap-4 rounded-card border border-line bg-surface px-4 py-3">
            <span className={`text-2xl ${i.ok ? "text-success" : i.required ? "text-danger" : "text-warn"}`}>{i.ok ? "✓" : i.required ? "✕" : "!"}</span>
            <span className="w-64 font-semibold text-white">{i.name}</span>
            <span className="text-muted">{i.detail}</span>
            {!i.required && <span className="ml-auto text-xs uppercase tracking-widest text-muted">optional</span>}
          </li>
        ))}
      </ul>
      <h2 className="text-lg font-bold uppercase tracking-widest text-muted">Manual checklist</h2>
      <ul className="flex flex-col gap-2">
        {MANUAL.map((m) => (
          <li key={m}>
            <label className="flex cursor-pointer items-center gap-3 rounded-card border border-line bg-surface px-4 py-3">
              <input type="checkbox" className="h-5 w-5 accent-[#2ECDDB]" checked={!!checked[m]} onChange={() => setChecked({ ...checked, [m]: !checked[m] })} />
              <span className={checked[m] ? "text-success" : "text-white"}>{m}</span>
            </label>
          </li>
        ))}
      </ul>
    </main>
  );
}
