/** X-ray: dim the shop page and reveal every hidden injection in place, glowing red, with a label.
 * Works because shop pages are served same-origin through the /shop rewrite. */
const STYLE_ID = "leash-xray-style";
const CSS = `
.leash-xray-reveal { display: none; }
body.leash-xray::before { content: ""; position: fixed; inset: 0; background: rgba(12, 8, 40, 0.6); z-index: 1; pointer-events: none; animation: lx-fade .2s ease-out; }
body.leash-xray .leash-xray-reveal {
  display: block; position: relative; z-index: 2; margin: 10px 0; padding: 10px 14px 12px;
  background: #fff1f3; border: 2px solid #ff5c7a; border-radius: 10px;
  box-shadow: 0 0 0 4px rgba(255,92,122,.25), 0 0 32px 6px rgba(255,92,122,.55);
  font: 15px/1.4 "JetBrains Mono", ui-monospace, monospace; color: #5a0d1c; animation: lx-fade .2s ease-out;
}
body.leash-xray .leash-xray-reveal .lx-chip {
  display: inline-block; margin-bottom: 6px; padding: 2px 8px; border-radius: 999px; background: #ff5c7a;
  color: #fff; font: 700 12px/1.4 Inter, system-ui, sans-serif; letter-spacing: .06em; text-transform: uppercase;
}
@keyframes lx-fade { from { opacity: 0 } to { opacity: 1 } }
`;

function injectionText(el: Element): string {
  const style = el.getAttribute("data-leash-injection");
  if (style === "html_comment") {
    const w = el.ownerDocument.createTreeWalker(el, NodeFilter.SHOW_COMMENT);
    const parts: string[] = [];
    while (w.nextNode()) parts.push((w.currentNode.nodeValue ?? "").trim());
    return parts.join(" ");
  }
  if (style === "alt_text") return el.querySelector("img")?.getAttribute("alt") ?? "";
  if (style === "json_ld") {
    const raw = el.querySelector("script")?.textContent ?? "";
    try {
      const j = JSON.parse(raw);
      return j.description ?? raw;
    } catch {
      return raw;
    }
  }
  return (el.textContent ?? "").trim();
}

export function applyXray(doc: Document | null | undefined, on: boolean): number {
  if (!doc?.body) return 0;
  if (!doc.getElementById(STYLE_ID)) {
    const s = doc.createElement("style");
    s.id = STYLE_ID;
    s.textContent = CSS;
    doc.head.appendChild(s);
  }
  const marks = Array.from(doc.querySelectorAll(".leash-inj"));
  for (const el of marks) {
    if (el.querySelector(":scope > .leash-xray-reveal")) continue;
    const box = doc.createElement("div");
    box.className = "leash-xray-reveal";
    const chip = doc.createElement("span");
    chip.className = "lx-chip";
    chip.textContent = el.getAttribute("data-label") ?? "hidden text";
    const text = doc.createElement("div");
    text.textContent = injectionText(el);
    box.append(chip, text);
    el.appendChild(box);
  }
  doc.body.classList.toggle("leash-xray", on);
  if (on && marks[0]) marks[0].scrollIntoView({ block: "center" });
  return marks.length;
}
