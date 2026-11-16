"""Pull the SEO-relevant facts out of one page's HTML. Standard library only."""

from __future__ import annotations

import html
import re
import urllib.parse
from html.parser import HTMLParser

WIX_DEFAULT_FAVICON = "parastorage.com/client/pfavico.ico"
CONNECT_DOMAIN_ERROR = "connectyourdomain"


class _Collector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.in_title = False
        self.meta: dict[str, str] = {}
        self.links: list[dict] = []
        self.images: list[dict] = []
        self.h1: list[str] = []
        self._h1_depth = 0
        self._h1_buf: list[str] = []
        self.lang = ""

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html":
            self.lang = a.get("lang", "")
        elif tag == "title":
            self.in_title = True
        elif tag == "meta":
            key = (a.get("name") or a.get("property") or "").lower()
            if key and key not in self.meta:
                self.meta[key] = a.get("content", "")
        elif tag == "link":
            self.links.append(a)
        elif tag == "img":
            self.images.append({"src": a.get("src", ""), "alt": a.get("alt"), "has_alt": "alt" in a})
        elif tag == "h1":
            self._h1_depth += 1
            self._h1_buf = []

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        elif tag == "h1" and self._h1_depth:
            self._h1_depth -= 1
            self.h1.append(re.sub(r"\s+", " ", "".join(self._h1_buf)).strip())

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)
        if self._h1_depth:
            self._h1_buf.append(data)


def media_key(src: str) -> str:
    """Wix serves one upload at many sizes; the media id identifies the image itself."""
    m = re.search(r"/media/([^/]+?)(?:~mv2)?\.\w+", src)
    if m:
        return m.group(1)
    return urllib.parse.urlsplit(src).path.rsplit("/", 1)[-1] or src


def file_name(src: str) -> str:
    return urllib.parse.unquote(urllib.parse.urlsplit(src).path.rsplit("/", 1)[-1])


def parse(page_html: str) -> dict:
    c = _Collector()
    try:
        c.feed(page_html)
    except Exception:  # malformed markup: keep what was read
        pass
    title = re.sub(r"\s+", " ", html.unescape("".join(c.title_parts))).strip()
    canonical = next((l.get("href", "") for l in c.links if l.get("rel", "").lower() == "canonical"), "")
    icon = next((l.get("href", "") for l in c.links if "icon" in l.get("rel", "").lower()), "")
    hreflang = [l.get("hreflang") for l in c.links if l.get("rel", "").lower() == "alternate" and l.get("hreflang")]
    # One entry per distinct image: Wix repeats an image at several sizes and in mobile layouts.
    seen: dict[str, dict] = {}
    for img in c.images:
        if not img["src"] or img["src"].startswith("data:"):
            continue
        key = media_key(img["src"])
        if key not in seen:
            seen[key] = {"image": key, "file": file_name(img["src"]), "alt": (img["alt"] or "").strip(),
                         "has_alt": img["has_alt"], "src": img["src"]}
    return {
        "title": title,
        "description": c.meta.get("description", "").strip(),
        "robots": c.meta.get("robots", "").lower(),
        "generator": c.meta.get("generator", ""),
        "og_title": c.meta.get("og:title", ""),
        "og_image": c.meta.get("og:image", ""),
        "og_site_name": c.meta.get("og:site_name", ""),
        "canonical": canonical,
        "favicon": icon,
        "hreflang": hreflang,
        "lang": c.lang,
        "h1": [h for h in c.h1 if h],
        "images": list(seen.values()),
        "is_wix": "wix.com" in c.meta.get("generator", "").lower(),
        "is_connect_domain_error": CONNECT_DOMAIN_ERROR in title.lower().replace(" ", ""),
    }
