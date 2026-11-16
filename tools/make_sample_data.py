"""Write the sample data: a fictional Wix florist site saved as local files, plus its old WordPress URLs.

Problems are planted on purpose so every check has something to find.

    python tools/make_sample_data.py
"""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "sample-data" / "willow-and-fern"
SITE = "https://www.willowandfern.example"
NAME = "Willow & Fern"
LOGO = ("static.wixstatic.com/media/a1b2c3_7f1e2d3c4b5a69788796a5b4c3d2e1f0~mv2.png", "Willow-Logo-Final.png")
DEFAULT_ICON = "https://static.parastorage.com/client/pfavico.ico"


def img(media: str, name: str, alt: str) -> str:
    return f'<img src="https://static.wixstatic.com/media/{media}~mv2.jpg/v1/fill/w_800,h_600/{name}" alt="{alt}"/>'


def page(title, desc, h1s, body_imgs, og_image="", robots="", canonical="", path="/"):
    meta = [f"<title>{title}</title>", '<meta name="generator" content="Wix.com Website Builder"/>',
            f'<meta property="og:site_name" content="{NAME}"/>', f'<meta property="og:title" content="{title}"/>',
            f'<link rel="icon" sizes="192x192" href="{DEFAULT_ICON}" type="image/x-icon"/>',
            f'<link rel="canonical" href="{canonical or SITE + (path if path != "/" else "")}"/>']
    if desc:
        meta.append(f'<meta name="description" content="{desc}"/>')
    if og_image:
        meta.append(f'<meta property="og:image" content="{og_image}"/>')
    if robots:
        meta.append(f'<meta name="robots" content="{robots}"/>')
    header = f'<header><img src="https://{LOGO[0]}/v1/fill/w_120,h_60/{LOGO[1]}" alt="{LOGO[1]}"/></header>'
    footer = ('<footer><img src="https://static.wixstatic.com/media/a1b2c3_insta000000000000000000000000~mv2.png/v1/'
              'fill/w_24,h_24/insta.png" alt="Instagram"/></footer>')
    heads = "".join(f"<h1><span>{h}</span></h1>" for h in h1s)
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"/>{"".join(meta)}</head><body>'
            f"{header}<main>{heads}{''.join(body_imgs)}<p>Sample page.</p></main>{footer}</body></html>")


PAGES = {
    "/": dict(title=NAME, desc="", h1s=["Flowers for every season"],
              imgs=[img("a1b2c3_4821aa", "IMG_4821.JPG", "IMG_4821.JPG")],
              og_image="https://static.wixstatic.com/media/a1b2c3_social~mv2.jpg"),
    "/about-3": dict(title=f"About | {NAME}", desc="About us.", h1s=["Our story"],
                     imgs=[img("a1b2c3_team01", "team.jpg", "Sara and Tom arranging peonies in the studio")]),
    "/weddings": dict(title=f"Wedding Flowers in Bath | {NAME}", desc="", h1s=[],
                      imgs=[img("a1b2c3_bouquet", "bridal-bouquet-peonies.jpg", "bridal-bouquet-peonies.jpg")]),
    "/copy-of-weddings": dict(title=f"Copy of Weddings | {NAME}",
                              desc="Small-group flower arranging workshops in our Bath studio, every Saturday morning.",
                              h1s=["Weddings"], imgs=[]),
    "/workshops": dict(title=f"Workshops | {NAME}",
                       desc="Small-group flower arranging workshops in our Bath studio, every Saturday morning.",
                       h1s=["Workshops", "Book a place"], imgs=[img("a1b2c3_ws", "workshop-table.jpg", "")]),
    "/contact": dict(title=f"Visit or Call Our Bath Flower Studio | {NAME}",
                     desc="Find our studio on Walcot Street, Bath. Opening hours, phone number and a map.",
                     h1s=["Contact"], imgs=[]),
    "/blank-1": dict(title=f"Blank | {NAME}", desc="", h1s=[], imgs=[], robots="noindex"),
    "/shop-1": dict(title=f"Shop | {NAME}", desc="", h1s=["Shop"], imgs=[], canonical=f"{SITE}/shop"),
    "/post/how-to-make-cut-flowers-last-longer": dict(
        title=f"How to Make Cut Flowers Last Longer | {NAME}",
        desc="Seven simple habits our florists use to keep a bouquet fresh for two weeks, from trimming to water.",
        h1s=["How to make cut flowers last longer"],
        imgs=[img("a1b2c3_shot", "Screenshot 2026-03-02 at 10.14.22.png", "Screenshot 2026-03-02 at 10.14.22.png")]),
    "/post/spring-wedding-flowers-guide": dict(
        title=f"The Complete Guide to Choosing Spring Wedding Flowers for Your Big Day | {NAME}",
        desc="Which flowers are in season for a spring wedding, what they cost, and how to pair them.",
        h1s=["Spring wedding flowers"], imgs=[]),
}
OLD_URLS = ["/", "/about-us/", "/wedding-flowers/", "/workshops/", "/contact/",
            "/2024/03/how-to-make-cut-flowers-last-longer/", "/2023/05/spring-wedding-flowers-guide/",
            "/shop/", "/flower-subscriptions/", "/gallery/", "/tag/peonies/",
            "/wp-content/uploads/2024/03/peonies.jpg"]
GSC = {"/": 5200, "/weddings": 3100, "/post/how-to-make-cut-flowers-last-longer": 2400, "/workshops": 900,
       "/about-3": 600, "/contact": 450, "/post/spring-wedding-flowers-guide": 300, "/shop-1": 120}


def urlset(paths):
    rows = "".join(f"<url><loc>{SITE}{'' if p == '/' else p}</loc><lastmod>2026-10-01</lastmod></url>" for p in paths)
    return f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" generatedBy="WIX">{rows}</urlset>'


def main() -> None:
    site = OUT / "new-wix-site"
    for path, p in PAGES.items():
        f = site / ("index.html" if path == "/" else path.strip("/") + ".html")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(page(p["title"], p["desc"], p["h1s"], p["imgs"], p.get("og_image", ""), p.get("robots", ""),
                          p.get("canonical", ""), path), encoding="utf-8")
    static = [p for p in PAGES if not p.startswith("/post/")]
    posts = [p for p in PAGES if p.startswith("/post/")]
    (site / "pages-sitemap.xml").write_text(urlset(static), encoding="utf-8")
    (site / "blog-posts-sitemap.xml").write_text(urlset(posts), encoding="utf-8")
    (site / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"<sitemap><loc>{SITE}/blog-posts-sitemap.xml</loc></sitemap>"
        f"<sitemap><loc>{SITE}/pages-sitemap.xml</loc></sitemap></sitemapindex>", encoding="utf-8")
    old = "".join(f"<url><loc>https://willowandfern-old.example{u}</loc></url>" for u in OLD_URLS)
    (OUT / "old-wordpress-sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{old}</urlset>',
        encoding="utf-8")
    with (OUT / "gsc_pages.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Top pages", "Clicks", "Impressions", "CTR", "Position"])
        for path, imp in GSC.items():
            w.writerow([SITE + ("/" if path == "/" else path), imp // 40, imp, f"{100 / 40:.1f}%", 6.2])
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
