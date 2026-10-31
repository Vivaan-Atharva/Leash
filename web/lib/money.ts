/** Money is integer paise. Format like the backend: 396000 -> "₹3,960", 4550 -> "₹45.50". */
export function inr(paise: number): string {
  const neg = paise < 0;
  const abs = Math.abs(Math.trunc(paise));
  const rupees = Math.floor(abs / 100);
  const p = abs % 100;
  const s = String(rupees);
  let grouped = s;
  if (s.length > 3) {
    let head = s.slice(0, -3);
    const tail = s.slice(-3);
    const parts: string[] = [];
    while (head.length > 2) {
      parts.unshift(head.slice(-2));
      head = head.slice(0, -2);
    }
    if (head) parts.unshift(head);
    grouped = parts.join(",") + "," + tail;
  }
  return `${neg ? "-" : ""}₹${grouped}${p ? "." + String(p).padStart(2, "0") : ""}`;
}
