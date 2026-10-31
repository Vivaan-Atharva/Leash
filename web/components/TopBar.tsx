"use client";
import { QRCodeSVG } from "qrcode.react";
import type { MandateInfo } from "@/lib/useLeash";
import { inr } from "@/lib/money";

export const hhmmss = (iso: string | null) =>
  iso ? new Date(iso).toLocaleTimeString("en-GB", { hour12: false }) : "";

const MODE_STYLE: Record<string, string> = {
  LIVE: "border-success text-success",
  REPLAY: "border-warn text-warn",
  SCRIPTED: "border-muted text-muted",
};

export function TopBar({ mode, model, connected, mandate, phoneUrl, moment }: {
  mode: string;
  model: string | null;
  connected: boolean;
  mandate: MandateInfo | null;
  phoneUrl: string | null;
  moment: string | null;
}) {
  const revoked = mandate?.status === "REVOKED";
  return (
    <header className="flex items-center gap-5 border-b border-line bg-surface px-6 py-2">
      <span className="text-[1.9em] font-black tracking-[0.18em] text-white" style={{ textShadow: "0 0 22px rgba(46,205,219,.55)" }}>
        LEASH
      </span>
      <span className={`flex items-center gap-2 rounded-full border-2 px-3 py-0.5 font-mono font-bold tracking-wider ${MODE_STYLE[mode] ?? MODE_STYLE.SCRIPTED}`}>
        <span className={`h-2.5 w-2.5 rounded-full bg-current ${mode === "LIVE" ? "animate-pulse" : ""}`} />
        {mode}
      </span>
      {model && mode === "LIVE" && <span className="font-mono text-[0.75em] text-muted">model: {model}</span>}
      {!connected && <span className="rounded-full bg-danger px-3 text-[0.8em] font-bold text-white">hub offline</span>}
      <div className="ml-auto flex items-center gap-4">
        {moment && <span className="font-mono text-[0.8em] text-muted">{moment}</span>}
        {mandate ? (
          <span className={`rounded-full border-2 px-4 py-1 font-medium ${revoked ? "border-danger text-danger" : "border-line text-body"}`}>
            Mandate: <span className="text-white">{mandate.user}</span> · {inr(mandate.per_order_paise)}/order · {inr(mandate.per_week_paise)}/wk
            {revoked && <span className="ml-2 font-bold">REVOKED {hhmmss(mandate.revoked_at)}</span>}
          </span>
        ) : (
          <span className="rounded-full border-2 border-line px-4 py-1 text-muted">No mandate</span>
        )}
        {phoneUrl && (
          <div className="flex items-center gap-2" title={phoneUrl}>
            <div className="rounded-md bg-white p-1">
              <QRCodeSVG value={phoneUrl} size={56} level="L" />
            </div>
            <span className="text-[0.65em] leading-tight text-muted">Asha&apos;s phone<br /><span className="font-mono">{phoneUrl.replace("http://", "")}</span></span>
          </div>
        )}
      </div>
    </header>
  );
}
