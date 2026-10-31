"use client";

import { use, useEffect, useState } from "react";
import { CHECK_LABEL } from "@/components/Pipeline";
import { api, getJSON } from "@/lib/hub";
import { inr } from "@/lib/money";
import { shopName } from "@/lib/friendly";
import { verifyBundle } from "@/lib/merkle";

type Report = any; // eslint-disable-line @typescript-eslint/no-explicit-any

const Tick = ({ ok, label }: { ok: boolean | null | undefined; label: string }) => (
  <span className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-0.5 text-sm font-semibold ${
    ok ? "border-success text-success" : ok === null || ok === undefined ? "border-line text-muted" : "border-danger text-danger"}`}>
    {ok ? "✓" : ok === null || ok === undefined ? "–" : "✕"} {label}
  </span>
);

function Section({ title, children, right }: { title: string; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <section className="report-card break-inside-avoid rounded-card border border-line bg-surface p-6">
      <div className="mb-4 flex items-center justify-between gap-4">
        <h2 className="text-lg font-bold uppercase tracking-widest text-muted">{title}</h2>
        {right}
      </div>
      {children}
    </section>
  );
}

const Row = ({ k, v, mono }: { k: string; v: React.ReactNode; mono?: boolean }) => (
  <div className="flex gap-4 border-b border-line/40 py-1.5 last:border-0">
    <span className="w-44 shrink-0 text-muted">{k}</span>
    <span className={`${mono ? "font-mono text-[0.9em]" : ""} text-white`}>{v}</span>
  </div>
);

const time = (iso?: string | null) => (iso ? new Date(iso).toLocaleString("en-IN", { hour12: false }) : "–");

export default function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [r, setR] = useState<Report | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [embed, setEmbed] = useState(false);
  const [trace, setTrace] = useState<any>(null); // eslint-disable-line @typescript-eslint/no-explicit-any

  useEffect(() => {
    setEmbed(new URLSearchParams(window.location.search).has("embed"));
    getJSON(api.gateway(`/report/${id}`))
      .then((rep) => {
        setR(rep);
        return getJSON(api.hub(`/trace/${rep.decision.request_id}`)).then(setTrace).catch(() => {});
      })
      .catch((e) => setErr(String(e)));
  }, [id]);

  if (err) return <main className="p-10 text-danger">Couldn&apos;t load report: {err}</main>;
  if (!r) return <main className="p-10 text-muted">Loading report…</main>;

  const d = r.decision, q = r.request, m = r.mandate, v = r.verdict;
  const mk = r.merkle ? verifyBundle(r.merkle) : null;
  const tone = v.tone === "allowed" ? "border-success text-success" : v.tone === "held" ? "border-warn text-warn" : "border-danger text-danger";
  return (
    <main className={`report mx-auto flex max-w-5xl flex-col gap-5 px-6 ${embed ? "py-6" : "py-10"}`}>
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-sm font-bold tracking-[0.3em] text-accent">LEASH · DISPUTE REPORT</div>
          <h1 className="mt-1 text-3xl font-bold text-white">Decision <span className="font-mono">{d.decision_id}</span></h1>
          <div className="mt-1 text-muted">{time(d.decided_at)} · {shopName(d.merchant)} ({d.merchant}) · request <span className="font-mono">{d.request_id}</span></div>
        </div>
        <button onClick={() => window.print()} className="no-print rounded-lg border border-line px-4 py-2 text-muted hover:text-white">Print</button>
      </header>

      <div className={`report-verdict rounded-card border-2 p-6 ${tone}`}>
        <div className="text-sm font-bold uppercase tracking-widest opacity-80">Verdict · {v.liability}</div>
        <div className="mt-2 text-2xl font-bold leading-snug">{v.headline}</div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Tick ok={r.signatures.mandate} label="mandate signed by Asha's phone" />
          <Tick ok={r.signatures.request} label="request signature valid" />
          <Tick ok={r.signatures.decision} label="decision signed by gateway" />
          <Tick ok={r.chain.ok && r.chain.decision_entry_matches} label="audit chain intact" />
          <Tick ok={mk ? mk.included && mk.signed : null} label="Merkle proof verified in this browser" />
        </div>
      </div>

      <div className="grid gap-5 md:grid-cols-2">
        <Section title="Signed mandate" right={<Tick ok={r.signatures.mandate} label="signature" />}>
          {m ? (
            <>
              <Row k="Mandate" v={`${m.mandate_id} · ${r.mandate_status}${r.revoked_at ? " at " + time(r.revoked_at) : ""}`} mono />
              <Row k="User" v={m.user.name} />
              <Row k="Shops" v={m.allowed_merchants.join(", ")} />
              <Row k="Categories" v={m.allowed_categories.join(", ")} />
              <Row k="Limits" v={`${inr(m.limits.per_order_paise)} per order · ${inr(m.limits.per_week_paise)} per week`} />
              <Row k="Shopping list" v={m.intent.items.map((i: any) => `${i.family} ×${i.max_qty} (${i.brands.join("/")})`).join(", ")} /> {/* eslint-disable-line @typescript-eslint/no-explicit-any */}
              <Row k="Valid" v={`${time(m.valid_from)} → ${time(m.valid_until)}`} />
              <Row k="Phone key" v={r.fingerprints.phone_key} mono />
              <Row k="Signature" v={r.fingerprints.mandate_signature} mono />
            </>
          ) : <div className="text-danger">No such mandate</div>}
        </Section>

        <Section title="Signed payment request" right={<Tick ok={r.signatures.request} label="signature" />}>
          <Row k="Merchant" v={q.merchant} mono />
          <div className="my-2 rounded-lg border border-line/60">
            {(q.cart ?? []).map((i: any) => ( // eslint-disable-line @typescript-eslint/no-explicit-any
              <div key={i.sku} className="flex justify-between border-b border-line/40 px-3 py-1.5 last:border-0">
                <span className="text-white">{i.brand} {i.family} <span className="text-muted">×{i.qty}</span></span>
                <span className="font-mono">{inr(i.claimed_unit_price_paise)} ea</span>
              </div>
            ))}
          </div>
          <Row k="Claimed total" v={typeof q.claimed_total_paise === "number" ? inr(q.claimed_total_paise) : "?"} />
          <Row k="Agent key" v={<>{r.fingerprints.agent_key} {r.signatures.request_key_in_mandate ? <span className="text-success">(in mandate)</span> : <span className="text-danger">(not in mandate)</span>}</>} mono />
          <Row k="Signature" v={r.fingerprints.request_signature} mono />
          <Row k="Created" v={time(q.created_at)} />
        </Section>
      </div>

      {trace?.trace && trace.trace.culprit !== null && (() => {
        const t = trace.trace, f = t.fields[t.culprit], p = f.prov;
        const cft = trace.counterfactual?.traces?.[trace.counterfactual.traces.length - 1];
        const cff = cft?.fields.find((x: any) => x.path === f.path) ?? cft?.fields.find((x: any) => x.field === f.field); // eslint-disable-line @typescript-eslint/no-explicit-any
        const show = (x: any) => (x.field === "price" ? inr(Number(x.value)) : x.field === "qty" ? `×${x.value}` : String(x.value)); // eslint-disable-line @typescript-eslint/no-explicit-any
        return (
          <Section title="Root cause (agent trace)" right={<span className="text-xs text-muted">explanation only · not used for the decision</span>}>
            <Row k="Tainted field" v={<span className="font-mono">{f.path} = <b className="text-danger">{show(f)}</b></span>} />
            <Row k="Came from" v={<>{p.label === "trusted" ? "Asha's task (trusted)" : `${p.how} on ${p.url ?? "the shop page"} (untrusted)`}</>} />
            {p.excerpt && <Row k="Text" v={<span className="font-mono text-sm">…{p.excerpt.before.slice(-80)}<mark className="rounded bg-danger px-1 text-white">{p.excerpt.match}</mark>{p.excerpt.after.slice(0, 80)}…</span>} />}
            {t.thought && <Row k="Agent's reasoning" v={<i>&ldquo;{t.thought}&rdquo;</i>} />}
            {cft && <Row k="Counterfactual" v={<>Same agent and task on the clean page: {cff ? <b>{show(cff)}</b> : null} · {inr(cft.total)} · Leash would say <b>{cft.right.outcome}</b>.{cff && String(cff.value) !== String(f.value) && <> The injection turned <b className="text-success">{show(cff)}</b> into <b className="text-danger">{show(f)}</b>.</>}</>} />}
          </Section>
        );
      })()}

      <Section title="Six checks" right={<span className="font-mono text-sm text-muted">profile {d.profile} · decided in {(d.decided_in_us / 1000).toFixed(1)} ms</span>}>
        <table className="w-full text-left">
          <tbody>
            {d.checks.map((c: any) => ( // eslint-disable-line @typescript-eslint/no-explicit-any
              <tr key={c.n} className="border-b border-line/40 last:border-0">
                <td className="w-10 py-2 font-mono text-muted">{c.n}</td>
                <td className="w-44 py-2 font-semibold text-white">{CHECK_LABEL[c.name] ?? c.name}</td>
                <td className={`w-20 py-2 font-bold ${c.pass ? "text-success" : "text-danger"}`}>{c.pass ? "✓ pass" : "✕ fail"}</td>
                <td className="py-2">{c.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-3 flex flex-wrap gap-6 text-sm">
          <span>Outcome: <b className="text-white">{d.outcome}</b></span>
          <span>Amount moved: <b className="text-white">{inr(r.resolution ? r.resolution.amount_debited_paise : d.amount_debited_paise)}</b></span>
          {d.step_up && <span>Step-up: <b className="text-warn">{d.step_up.reason}</b></span>}
          {r.resolution && <span>Resolved by <b className="text-white">{r.resolution.resolved_by}</b> at {time(r.resolution.resolved_at)} → <b>{r.resolution.outcome}</b></span>}
          <span className="font-mono text-muted">gateway signature {r.fingerprints.decision_signature}</span>
        </div>
      </Section>

      <div className="grid gap-5 md:grid-cols-2">
        <Section title="Audit chain" right={<Tick ok={r.chain.ok} label={r.chain.ok ? "intact" : `broken at #${r.chain.broken_at}`} />}>
          <Row k="Entries verified" v={`#1 to #${r.chain.length}`} />
          <Row k="This decision" v={`log #${d.log_index} · ${r.chain.decision_entry_matches ? "matches the signed record" : "DOES NOT MATCH"}`} />
          <Row k="Entry hash" v={`${(d.log_hash ?? "").slice(0, 24)}…`} mono />
          <Row k="Gateway key" v={r.fingerprints.gateway_key} mono />
        </Section>
        <Section title="Transparency log" right={<Tick ok={mk ? mk.included && mk.signed : null} label="checked here, not by the server" />}>
          {r.merkle && mk ? (
            <>
              <Row k="Leaf" v={<>entry #{r.merkle.entry?.index} → SHA-256 <span className="font-mono">{mk.leaf.slice(0, 16)}…</span></>} />
              <Row k="Proof path" v={<span className="flex flex-wrap gap-1">{r.merkle.proof.map((h: string, i: number) => <span key={i} className="rounded border border-line px-1.5 font-mono text-xs">{h.slice(0, 8)}</span>)}{r.merkle.proof.length === 0 && "—"}</span>} />
              <Row k="Root" v={<span className="font-mono">{r.merkle.sth.root_hash.slice(0, 24)}… {mk.included ? <span className="text-success">✓ matches</span> : <span className="text-danger">✕ does not match</span>}</span>} />
              <Row k="Signed tree head" v={<>size {r.merkle.sth.tree_size} · {mk.signed ? <span className="text-success">✓ gateway signature valid</span> : <span className="text-danger">✕ bad signature</span>}</>} />
              <div className="mt-2 text-xs text-muted">Certificate-Transparency-style log (RFC 6962). Your browser recomputed the leaf from the entry, walked the proof to the root, and checked the gateway&apos;s Ed25519 signature on the tree head.</div>
            </>
          ) : <div className="text-muted">No proof available.</div>}
        </Section>
      </div>

      <div className="grid gap-5 md:grid-cols-1">
        <Section title="Timeline">
          {r.timeline.map((t: any) => ( // eslint-disable-line @typescript-eslint/no-explicit-any
            <div key={t.index} className="flex gap-3 border-b border-line/40 py-1.5 font-mono text-sm last:border-0">
              <span className="w-10 text-muted">#{t.index}</span>
              <span className="w-24 text-muted">{new Date(t.timestamp).toLocaleTimeString("en-GB")}</span>
              <span className="flex-1 text-white">{t.type.replaceAll("_", " ").toLowerCase()}</span>
              <span className="text-muted">{t.hash.slice(0, 8)}…</span>
            </div>
          ))}
        </Section>
      </div>
      <footer className="pb-6 text-center text-sm text-muted">
        Every record above is signed and hash-chained. Re-verify with GET /report/{d.decision_id} on the Leash gateway.
      </footer>
    </main>
  );
}
