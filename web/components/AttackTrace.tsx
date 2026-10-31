"use client";
/** Attack trace: follow one tainted value from the page to the money, then show the counterfactual. */
import { AnimatePresence, motion } from "framer-motion";
import type { AttackTrace as Trace, Counterfactual, Prov, TraceField } from "@/lib/useLeash";
import { inr } from "@/lib/money";
import { CHECK_LABEL } from "./Pipeline";

const STEP = 0.45; // seconds between stages lighting up

function Chip({ prov }: { prov: Prov }) {
  const cls =
    prov.label === "trusted" ? "border-success text-success" :
    prov.hidden ? "border-danger bg-danger text-white" :
    prov.label === "untrusted" ? "border-warn text-warn" : "border-line text-muted";
  return (
    <span className={`inline-block rounded-full border px-2 py-[1px] text-[0.62em] font-bold uppercase tracking-wider ${cls}`}>
      {prov.label === "trusted" ? "trusted · your task" : prov.label === "untrusted" ? `untrusted · ${prov.how}` : prov.how}
    </span>
  );
}

function Excerpt({ prov, max = 140 }: { prov: Prov; max?: number }) {
  if (!prov.excerpt) return null;
  const { before, match, after } = prov.excerpt;
  return (
    <span className="font-mono text-[0.78em] leading-snug">
      {before.length > max / 2 ? "…" + before.slice(-max / 2) : before}
      <mark className="rounded bg-danger px-1 font-bold text-white">{match}</mark>
      {after.length > max / 2 ? after.slice(0, max / 2) + "…" : after}
    </span>
  );
}

function Stage({ n, title, sub, children, i, danger }: { n: number; title: string; sub?: string; children: React.ReactNode; i: number; danger?: boolean }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: i * STEP, duration: 0.3 }}
      className={`relative flex min-w-0 flex-col gap-2 rounded-card border-2 bg-surface p-3 ${danger ? "border-danger/80" : "border-line"}`}
    >
      <div className="flex items-baseline gap-2">
        <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[0.75em] font-black ${danger ? "bg-danger text-white" : "bg-line text-white"}`}>{n}</span>
        <span className="font-black tracking-widest text-white">{title}</span>
      </div>
      {sub && <div className="text-[0.72em] text-muted">{sub}</div>}
      <div className="min-w-0">{children}</div>
    </motion.div>
  );
}

function highlight(text: string, needle: string | undefined) {
  if (!needle) return text;
  const i = text.toLowerCase().indexOf(needle.toLowerCase());
  if (i < 0) return text;
  return (
    <>
      {text.slice(0, i)}
      <mark className="rounded bg-danger px-1 font-bold text-white">{text.slice(i, i + needle.length)}</mark>
      {text.slice(i + needle.length)}
    </>
  );
}

const fieldValue = (f?: TraceField) => (f ? (f.field === "price" ? inr(Number(f.value)) : f.field === "qty" ? `×${f.value}` : String(f.value)) : "");

export function AttackTraceOverlay({ open, trace, cf, cfRunning, onClose }: {
  open: boolean; trace: Trace | null; cf: Counterfactual | null; cfRunning: boolean; onClose: () => void;
}) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="absolute inset-x-0 bottom-0 top-[64px] z-40 overflow-y-auto bg-bg px-6 py-4">
          {!trace ? (
            <div className="flex h-full items-center justify-center text-[1.3em] text-muted">No payment request yet. Run a scenario, then press A.</div>
          ) : (
            <Body key={trace.request_id} t={trace} cf={cf} cfRunning={cfRunning} onClose={onClose} />
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function Body({ t, cf, cfRunning, onClose }: { t: Trace; cf: Counterfactual | null; cfRunning: boolean; onClose: () => void }) {
  const f = t.culprit !== null ? t.fields[t.culprit] : undefined;
  const p = f?.prov;
  const blocked = t.right.outcome !== "ALLOWED";
  const fails = t.right.checks.filter((c) => !c.pass);
  const needle = p?.excerpt?.match;
  const ctx = t.page?.segments ?? [];
  const src = t.source && !t.source.trusted ? t.source : null;
  // Context shown: the culprit's exact source (from whichever page it was read on), then other hidden lines.
  const others = ctx.filter((s) => s.hidden && s.id !== src?.id).slice(0, src ? 2 : 3);
  const cfTrace = cf?.traces?.[cf.traces.length - 1];
  const cfField = cfTrace && f ? cfTrace.fields.find((x) => x.path === f.path) ?? cfTrace.fields.find((x) => x.field === f.field) : undefined;
  const attack = !!f && p?.label !== "trusted";

  return (
    <div className="mx-auto flex max-w-[1840px] flex-col gap-3">
      <div className="flex items-baseline gap-4">
        <h2 className="text-[1.6em] font-black tracking-[0.15em] text-white">ATTACK TRACE</h2>
        <span className="font-mono text-muted">{t.scenario ?? ""} · {t.request_id}</span>
        {f && <span className="text-[1.05em]">following <b className="rounded bg-danger px-2 font-mono text-white">{f.path} = {fieldValue(f)}</b></span>}
        <button onClick={onClose} className="ml-auto rounded-lg border border-line px-3 py-1 text-muted hover:text-white">Close (A)</button>
      </div>

      {/* the thread */}
      <div className="relative h-1.5 overflow-hidden rounded-full bg-line/40">
        <motion.div className={`absolute inset-y-0 left-0 rounded-full ${attack ? "bg-danger" : "bg-success"}`}
          initial={{ width: "0%" }} animate={{ width: "100%" }} transition={{ duration: STEP * 5, ease: "linear" }} />
      </div>

      <div className="grid grid-cols-5 gap-3">
        <Stage n={1} i={0} title="THE PAGE" sub={t.page ? `${t.page.url} · what Asha would see is not what the agent reads` : "no page"} danger={!!p?.hidden}>
          {p?.excerpt && p.label === "untrusted" ? (
            <div className="flex flex-col gap-1.5">
              <Chip prov={p} />
              <Excerpt prov={p} />
              {p.hidden && <div className="text-[0.72em] text-danger">Invisible to a person. A scraper keeps it.</div>}
            </div>
          ) : (
            <div className="text-[0.85em] text-muted">{f?.field === "price" ? "The shop set this price itself." : "Nothing hidden drove this request."}</div>
          )}
        </Stage>

        <Stage n={2} i={1} title="AGENT'S CONTEXT" sub="everything the model read, with its source label" danger={!!src}>
          <div className="flex flex-col gap-1">
            {t.task && (
              <div className="rounded-md border border-success/60 px-2 py-1">
                <div className="text-[0.6em] font-bold uppercase tracking-wider text-success">trusted · your task</div>
                <div className="truncate text-[0.75em]">{t.task}</div>
              </div>
            )}
            {src && (
              <div className="rounded-md border border-danger bg-danger/15 px-2 py-1">
                <div className="text-[0.6em] font-bold uppercase tracking-wider text-danger">untrusted · {src.hidden ?? "visible page text"} · {src.url}</div>
                <div className="line-clamp-3 font-mono text-[0.72em]">{highlight(src.text, needle)}</div>
              </div>
            )}
            {others.map((s) => (
              <div key={s.id} className="rounded-md border border-warn/50 px-2 py-1">
                <div className="text-[0.6em] font-bold uppercase tracking-wider text-warn">untrusted · {s.hidden}</div>
                <div className="line-clamp-2 font-mono text-[0.72em]">{s.text}</div>
              </div>
            ))}
            <div className="text-[0.65em] text-muted">+ {Math.max(0, ctx.length - others.length - (src ? 1 : 0))} more page lines, all untrusted</div>
          </div>
        </Stage>

        <Stage n={3} i={2} title="REASONING" sub="the model, in its own words" danger={attack}>
          <div className="rounded-md bg-bg/60 p-2 text-[0.9em] italic text-white">
            {t.thought ? <>&ldquo;{highlight(t.thought, needle && t.thought.toLowerCase().includes(needle.toLowerCase()) ? needle : String(f?.value ?? ""))}&rdquo;</> : "—"}
          </div>
        </Stage>

        <Stage n={4} i={3} title="TOOL CALL" sub="what the model decided to do" danger={attack}>
          {t.call ? (
            <div className="font-mono text-[0.8em] leading-relaxed">
              <span className="text-accent">{t.call.tool}</span>(
              {Object.entries(t.call.args ?? {}).map(([k, v], j, arr) => {
                const hit = f && String(v).toLowerCase().includes(String(f.field === "merchant" ? "" : f.value).toLowerCase()) && (k === f.field || (f.field === "merchant" && k === "shop"));
                return (
                  <span key={k}>
                    {k}=<span className={hit ? "rounded bg-danger px-1 font-bold text-white" : "text-white"}>{String(v)}</span>
                    {j < arr.length - 1 ? ", " : ""}
                  </span>
                );
              })}
              )
              {p && <div className="mt-2"><Chip prov={p} /></div>}
            </div>
          ) : <div className="text-muted">—</div>}
        </Stage>

        <Stage n={5} i={4} title="SIGNED REQUEST" sub="agent's signature ✓ valid. The signature is genuine; the intent isn't." danger={attack}>
          <div className="flex flex-col gap-1 text-[0.78em]">
            {t.fields.filter((x) => x.field !== "sku" || x === f).map((x) => (
              <div key={x.path} className={`flex items-center justify-between gap-2 rounded px-1.5 py-0.5 ${x === f ? "bg-danger/25 ring-1 ring-danger" : ""}`}>
                <span className="truncate font-mono">{x.path.replace("claimed_unit_price_paise", "price")} = <b className="text-white">{fieldValue(x)}</b></span>
                <span className={`shrink-0 text-[0.75em] ${x.prov.label === "trusted" ? "text-success" : x.prov.hidden ? "text-danger" : "text-warn"}`}>
                  {x.prov.label === "trusted" ? "task" : x.prov.hidden ? "hidden" : x.prov.label === "untrusted" ? "page" : "?"}
                </span>
              </div>
            ))}
            <div className="mt-1 border-t border-line pt-1 font-mono">total <b className="text-white">{inr(t.total)}</b></div>
          </div>
        </Stage>
      </div>

      {/* the split */}
      <motion.div className="grid grid-cols-2 gap-3" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: STEP * 5 + 0.1 }}>
        <div className="rounded-card border-2 border-danger/80 bg-danger/10 p-4">
          <div className="font-black tracking-widest text-danger">NO LEASH · the rail checks only the signature</div>
          <div className="mt-1 text-[2.2em] font-black text-danger">{t.left.amount_paise ? `${inr(t.left.amount_paise)} paid` : "₹0"}</div>
          <div className="text-[0.85em] text-muted">A valid agent signature is all it needs. Nothing compares the request to what Asha asked for.</div>
        </div>
        <div className={`rounded-card border-2 p-4 ${blocked ? "border-success/80 bg-success/10" : "border-warn/70 bg-warn/10"}`}>
          <div className="font-black tracking-widest text-success">WITH LEASH · the request is checked against Asha&apos;s signed mandate</div>
          <div className={`mt-1 text-[2.2em] font-black ${t.right.outcome === "BLOCKED" ? "text-success" : "text-warn"}`}>
            {t.right.outcome === "BLOCKED" ? "BLOCKED · ₹0 moved" : t.right.outcome === "HELD" ? "HELD for Asha's approval" : `ALLOWED · ${inr(t.right.amount_paise)}`}
          </div>
          {fails.slice(0, 2).map((c) => (
            <div key={c.n} className="text-[0.9em]"><b className="text-danger">Check {c.n} · {CHECK_LABEL[c.name]}:</b> {c.detail}</div>
          ))}
        </div>
      </motion.div>

      {/* the counterfactual */}
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: STEP * 6 + 0.2 }}
        className="rounded-card border-2 border-accent/70 bg-surface p-4">
        <div className="flex items-baseline gap-3">
          <span className="font-black tracking-widest text-accent">COUNTERFACTUAL</span>
          <span className="text-[0.85em] text-muted">same agent · same task · the same page with the hidden text removed and honest prices · dry run, no money moves{cf?.mode ? ` · ${cf.mode.toUpperCase()}` : ""}</span>
        </div>
        {cfTrace ? (
          <div className="mt-2 flex flex-wrap items-center gap-x-6 gap-y-1 text-[1.05em]">
            <span>It buys <b className="text-white">{cfTrace.fields.filter((x) => x.field === "sku").map((x) => {
              const q = cfTrace.fields.find((y) => y.path === x.path.replace(".sku", ".qty"));
              return `${x.display.replace(/ \(.*\)$/, "")} ${fieldValue(q)}`;
            }).join(", ")}</b> at <b className="text-white">{cfTrace.fields[0]?.display}</b> for <b className="text-white">{inr(cfTrace.total)}</b></span>
            <span className={`rounded-full border-2 px-3 font-bold ${cfTrace.right.outcome === "ALLOWED" ? "border-success text-success" : "border-warn text-warn"}`}>
              Leash would say {cfTrace.right.outcome}
            </span>
            {f && cfField && String(cfField.value) !== String(f.value) && (
              <span className="text-[1.1em] font-bold text-white">
                The hidden text turned <span className="text-success">{fieldValue(cfField)}</span> into <span className="text-danger">{fieldValue(f)}</span>.
              </span>
            )}
          </div>
        ) : (
          <div className="mt-2 text-muted">{cfRunning ? "Re-running the agent on the clean page…" : "No counterfactual for this request (no attack on the page)."}</div>
        )}
      </motion.div>
      <div className="text-[0.7em] text-muted">
        Trace from the agent runtime&apos;s provenance ledger (CaMeL / FIDES-style source labels, matched by value). It explains the attack; Leash&apos;s decision never uses it.
      </div>
    </div>
  );
}
