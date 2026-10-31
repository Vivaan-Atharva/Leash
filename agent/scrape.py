"""What a scraper sees: visible text plus hidden text, comments, alt text and JSON-LD.

That's realistic (scrapers keep this stuff) and it's how injections reach the model.
`scrape_segments` also says *how* each piece was hidden from a human, judged from the markup
itself (CSS, aria-hidden, comments, alt, JSON-LD), so the attack trace can point at it.
"""
import re
from html.parser import HTMLParser

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


def _hidden_reason(tag: str, a: dict) -> str | None:
    style = re.sub(r"\s+", "", (a.get("style") or "").lower())
    if "display:none" in style or "visibility:hidden" in style:
        return "display:none text"
    if re.search(r"(^|;)color:(#fff\b|#ffffff\b|white\b)", style) and re.search(r"background(-color)?:(#fff\b|#ffffff\b|white\b)", style):
        return "white-on-white text"
    m = re.search(r"font-size:(\d+(?:\.\d+)?)px", style)
    if m and float(m.group(1)) <= 3:
        return "near-invisible text"
    if a.get("aria-hidden") == "true":
        return "aria-hidden text"
    if tag == "script" and a.get("type") == "application/ld+json":
        return "JSON-LD metadata"
    return None


class _Scraper(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.segments: list[dict] = []  # {"text", "hidden": str|None}
        self._stack: list[tuple[str, str | None, bool]] = []  # (tag, hidden reason, skip)

    def _cur(self) -> tuple[str | None, bool]:
        return (self._stack[-1][1], self._stack[-1][2]) if self._stack else (None, False)

    def _add(self, text: str, hidden: str | None) -> None:
        text = text.strip()
        if text:
            self.segments.append({"text": text, "hidden": hidden})

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        parent_hidden, parent_skip = self._cur()
        if tag == "img" and a.get("alt"):
            self._add(a["alt"], parent_hidden or "image alt text")
        if tag in VOID:
            return
        skip = parent_skip or tag == "style" or (tag == "script" and a.get("type") != "application/ld+json")
        self._stack.append((tag, parent_hidden or _hidden_reason(tag, a), skip))

    def handle_endtag(self, tag):
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                del self._stack[i:]
                break

    def handle_data(self, data):
        hidden, skip = self._cur()
        if not skip:
            self._add(data, hidden)

    def handle_comment(self, data):
        self._add(data, "HTML comment")


def scrape_segments(html: str) -> list[dict]:
    p = _Scraper()
    p.feed(html)
    return p.segments


def scrape_text(html: str) -> str:
    return "\n".join(s["text"] for s in scrape_segments(html))
