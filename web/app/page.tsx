import Link from "next/link";

const LINKS = [
  ["/control", "Mission Control", "the stage demo (projector)"],
  ["/phone", "Asha's phone", "sign the mandate, revoke, approve"],
  ["/attack", "Try to trick it", "write your own injection"],
  ["/results", "Results", "measured attack suite"],
  ["/preflight", "Preflight", "is everything ready?"],
  ["/control?table=1", "Table demo", "60 seconds: S1, then results"],
];

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-8 px-6">
      <h1 className="text-6xl font-black tracking-[0.18em] text-white">LEASH</h1>
      <p className="max-w-xl text-center text-muted">The agent doesn&apos;t have a key that moves money. Only the gateway does.</p>
      <div className="grid w-full max-w-3xl gap-3 sm:grid-cols-2">
        {LINKS.map(([href, name, sub]) => (
          <Link key={href} href={href} className="rounded-card border border-line bg-surface px-5 py-4 hover:border-accent">
            <div className="text-lg font-bold text-white">{name}</div>
            <div className="text-sm text-muted">{sub}</div>
          </Link>
        ))}
      </div>
    </main>
  );
}
