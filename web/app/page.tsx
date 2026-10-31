import Link from "next/link";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-[#1B1249] text-white">
      <h1 className="text-5xl font-bold">LEASH</h1>
      <Link className="text-[#2ECDDB] underline" href="/control">Mission Control →</Link>
    </main>
  );
}
