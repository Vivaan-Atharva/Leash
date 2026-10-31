"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChainBar } from "@/components/ChainBar";
import { LeftLane, RightLane } from "@/components/Lanes";
import { DirectorBanner, ReportOverlay, Totals } from "@/components/Overlays";
import { Packet } from "@/components/Packet";
import { RevokeSnap } from "@/components/RevokeSnap";
import { ShopView } from "@/components/ShopView";
import { ThoughtStream } from "@/components/ThoughtStream";
import { TopBar, hhmmss } from "@/components/TopBar";
import { api, getJSON, postJSON } from "@/lib/hub";
import { useLeash } from "@/lib/useLeash";

const MOMENT_NAMES: Record<string, string> = {
  S0: "Honest purchase", S1: "40 packs", S2: "Look-alike shop", S3: "3× price", S4: "Hidden gift card",
  REVOKE: "Pull the leash", S5: "After revoke", TOTALS: "Totals", REPORT: "Dispute report", RESULTS: "Results",
  S6: "Order splitting", S7: "Replay", S8: "Unregistered agent", S9: "In-scope steering",
};

export default function MissionControl() {
  const { state, refresh } = useLeash();
  const [xray, setXray] = useState(false);
  const [phoneUrl, setPhoneUrl] = useState<string | null>(null);
  const [verifyFlash, setVerifyFlash] = useState(0);
  const [totalsOpen, setTotalsOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [reportId, setReportId] = useState<string | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const cartRef = useRef<HTMLDivElement>(null);
  const leftRef = useRef<HTMLDivElement>(null);
  const rightRef = useRef<HTMLDivElement>(null);

  const say = (t: string) => {
    setToast(t);
    setTimeout(() => setToast(null), 2200);
  };

  useEffect(() => {
    getJSON(api.hub("/netinfo")).then((n) => setPhoneUrl(n.phone_url)).catch(() => {});
  }, []);
  useEffect(() => {
    setXray(false);
  }, [state.shop.url]);
  useEffect(() => {
    setTotalsOpen(state.director.moment === "TOTALS" && state.director.status === "totals");
    if (state.director.status === "report") {
      if (state.director.decision_id) setReportId(state.director.decision_id);
      else say("No blocked decision to report yet");
    }
    if (state.director.status === "results") window.location.href = "/results?from=control";
  }, [state.director]);

  const director = useCallback(async (path: string) => {
    try {
      const r = await postJSON(api.hub(path));
      if (r.busy) say("Agent is still running…");
    } catch (e) {
      say(String(e));
    }
  }, []);

  const tamper = useCallback(async () => {
    try {
      await postJSON(api.gateway(state.tampered ? "/demo/restore" : "/demo/tamper"));
    } catch (e) {
      say(String(e));
    }
  }, [state.tampered]);

  const verify = useCallback(async () => {
    await refresh();
    setVerifyFlash((n) => n + 1);
  }, [refresh]);

  const reset = useCallback(async () => {
    if (!window.confirm("Reset the demo? Fresh balances, fresh log, seed mandate.")) return;
    setTotalsOpen(false);
    await postJSON(api.hub("/demo/reset"));
  }, []);

  const toggleMode = useCallback(async () => {
    const next = state.mode === "LIVE" ? "REPLAY" : "LIVE";
    await postJSON(api.hub("/mode"), { mode: next });
    say(`Next run: ${next}`);
  }, [state.mode]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key;
      if (k === "ArrowRight" || k === " " || k === "PageDown") {
        e.preventDefault();
        setTotalsOpen(false);
        setReportId(null);
        director("/director/next");
      } else if (k === "ArrowLeft" || k === "PageUp") {
        e.preventDefault();
        director("/director/prev");
      } else if (/^[0-9]$/.test(k)) director(`/director/scenario/S${k}`);
      else if (k === "x" || k === "X") setXray((v) => !v);
      else if (k === "t" || k === "T") tamper();
      else if (k === "r" || k === "R") reset();
      else if (k === "l" || k === "L") toggleMode();
      else if (k === "f" || k === "F") {
        if (document.fullscreenElement) document.exitFullscreen();
        else document.documentElement.requestFullscreen().catch(() => {});
      } else if (k === "Escape") {
        setTotalsOpen(false);
        setReportId(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [director, tamper, reset, toggleMode]);

  const d = state.director;
  const label = d.moment ? `${d.index >= 0 ? `${d.index + 1}/${(d as { of?: number }).of ?? 9} · ` : ""}${d.moment} ${MOMENT_NAMES[d.moment] ?? ""}` : null;
  const revoked = state.mandate?.status === "REVOKED";

  return (
    <div ref={root} className="relative flex h-screen min-h-[720px] flex-col overflow-hidden text-[clamp(13px,0.95vw,20px)]">
      <TopBar mode={state.mode} model={state.model} connected={state.connected} mandate={state.mandate} phoneUrl={phoneUrl} moment={label} />

      <main className="grid min-h-0 flex-1 grid-cols-[1fr_1.45fr_1fr] gap-5 px-6 py-4 short:py-2">
        <LeftLane balance={state.left.balance} payments={state.left.payments} lost={state.score.left_lost_paise} targetRef={leftRef} />

        <section className="flex min-h-0 flex-col gap-3">
          <h2 className="flex items-baseline gap-3 text-[1.3em] font-black tracking-[0.2em] text-accent">
            THE AGENT <span className="text-[0.6em] font-medium tracking-normal text-muted">one brain, both wallets</span>
          </h2>
          <div className="flex min-h-0 basis-[32%] flex-col"><ThoughtStream lines={state.lines} /></div>
          <ShopView url={state.shop.url} merchant={state.shop.merchant} injections={state.shop.injections} xray={xray} onToggle={() => setXray((v) => !v)} />
          <div ref={cartRef} className="flex items-center gap-3 rounded-card border border-line bg-surface px-4 py-3">
            <span className="font-semibold text-white">Cart</span>
            {state.cart ? (
              <>
                <span className="min-w-0 truncate">
                  {state.cart.items.map((i) => `${i.brand} ${i.family} ×${i.qty}`).join(", ")}
                </span>
                <span className="shrink-0 whitespace-nowrap font-mono text-muted">@ {state.cart.merchant}</span>
                <span className="ml-auto shrink-0 font-mono text-[1.2em] font-bold text-white">{state.cart.amount}</span>
                <span className="hidden shrink-0 whitespace-nowrap text-accent 2xl:inline">→ signed request</span>
              </>
            ) : (
              <span className="text-muted">empty</span>
            )}
          </div>
        </section>

        <div className="relative flex min-h-0 flex-col">
          <RightLane balance={state.right.balance} decision={state.right.decision} pending={!!state.right.pending}
            lost={state.score.right_lost_paise} targetRef={rightRef} onOpen={setReportId} />
          <RevokeSnap seq={state.revokeSeq} time={revoked ? hhmmss(state.mandate?.revoked_at ?? null) : null} />
        </div>
      </main>

      <ChainBar chain={state.chain} verify={state.verify} tampered={state.tampered} onVerify={verify} onTamper={tamper} flash={verifyFlash} />

      <Packet id={state.packet ? `${state.packet.id}-${state.packet.seq}` : null} root={root} from={cartRef} left={leftRef} right={rightRef} />
      <DirectorBanner director={d} revoked={revoked} />
      <Totals open={totalsOpen} left={state.score.left_lost_paise} right={state.score.right_lost_paise} onClose={() => setTotalsOpen(false)} />
      <ReportOverlay id={reportId} onClose={() => setReportId(null)} />
      {toast && <div className="absolute bottom-24 right-6 z-50 rounded-lg border border-line bg-surface px-4 py-2">{toast}</div>}
    </div>
  );
}
