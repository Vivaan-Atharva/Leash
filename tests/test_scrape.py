from agent.scrape import scrape_text
from shops.app import STATE, render_injection, INJECTIONS


def test_scraper_sees_hidden_text():
    html = ('<p>Visible</p><!-- comment note --><img alt="alt note">'
            '<div style="display:none">hidden note</div><style>.x{}</style>'
            '<script>var x=1</script><script type="application/ld+json">{"d":"ld note"}</script>')
    t = scrape_text(html)
    for s in ("Visible", "comment note", "alt note", "hidden note", "ld note"):
        assert s in t
    assert "var x" not in t and ".x{}" not in t


def test_every_injection_style_reaches_the_scraper_and_is_marked():
    for sc in INJECTIONS.values():
        for inj in sc["injections"]:
            html = render_injection(inj)
            assert 'class="leash-inj"' in html
            assert inj["text"].split()[0] in scrape_text(html)
