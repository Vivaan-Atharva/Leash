import { inr } from "./money";

export const SHOP_NAME: Record<string, string> = {
  "freshcart.in": "FreshCart",
  "dailybasket.in": "DailyBasket",
  "fresh-kart.in": "FreshKart",
};
export const shopName = (m: string) => SHOP_NAME[m] ?? m;

type Dec = { outcome: string; amount_paise: number; merchant: string; checks?: { n: number; name: string; pass: boolean; detail: string }[] };

/** One plain-English line for Asha's phone. */
export function friendly(d: Dec): string {
  if (d.outcome === "ALLOWED") return `Allowed ${inr(d.amount_paise)} · ${shopName(d.merchant)}`;
  if (d.outcome === "HELD") return `Waiting for your approval · ${shopName(d.merchant)}`;
  const f = d.checks?.find((c) => !c.pass);
  if (!f) return "Blocked";
  const det = f.detail;
  switch (f.n) {
    case 1:
      return "Blocked · an unknown agent tried to pay";
    case 2:
      return det.includes(`${d.merchant} not in mandate`)
        ? `Blocked · ${shopName(d.merchant)} isn't one of your shops`
        : "Blocked · that isn't on your shopping list";
    case 3:
      return det.includes("weekly") ? "Blocked · over your weekly limit" : "Blocked · over your per-order limit";
    case 4:
      return det.includes("×") ? "Blocked · far more than you asked for" : "Blocked · not on your shopping list";
    case 5: {
      const m = det.match(/\+(\d+)%/);
      const x = m ? (1 + Number(m[1]) / 100).toFixed(m && Number(m[1]) % 100 === 0 ? 0 : 1) : null;
      return x ? `Blocked · price ${x}× above normal` : "Blocked · price above normal";
    }
    case 6:
      return det.includes("revoked") ? "Blocked · you pulled the leash" : det.includes("replayed") ? "Blocked · a repeated request" : "Blocked · mandate not valid";
  }
  return "Blocked";
}
