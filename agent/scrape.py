"""What a scraper sees: visible text plus hidden text, comments, alt text and JSON-LD.

That's realistic (scrapers keep this stuff) and it's how injections reach the model.
"""
from html.parser import HTMLParser


class _Scraper(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._skip = 0  # inside <style> or a non-JSON-LD <script>

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "style" or (tag == "script" and a.get("type") != "application/ld+json"):
            self._skip += 1
        if tag == "img" and a.get("alt"):
            self.out.append(a["alt"])

    def handle_endtag(self, tag):
        if tag in ("style", "script") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.out.append(data.strip())

    def handle_comment(self, data):
        if data.strip():
            self.out.append(data.strip())


def scrape_text(html: str) -> str:
    p = _Scraper()
    p.feed(html)
    return "\n".join(p.out)
