"""Read a site politely: robots.txt first, one request at a time, a pause between requests.

A source is either a live site (https://...) or a local folder that mirrors one, which is
how the tests and the sample data run. In a local folder, "/" is index.html, "/about" is
about.html, "/post/x" is post/x.html and sitemaps keep their own file names.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

USER_AGENT = "WixSiteDoctor/1.0 (site audit; respects robots.txt)"
SM_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


@dataclass
class Response:
    url: str          # the URL asked for
    final_url: str    # after redirects
    status: int       # 0 when the request failed outright
    text: str
    error: str = ""


class Source:
    """Fetches pages from a live site or from a local mirror folder."""

    def __init__(self, base: str, delay: float = 1.0, timeout: float = 20.0):
        self.local = None
        p = Path(base).expanduser()
        if p.is_dir():
            self.local = p
            self.origin = "https://local.example"
        else:
            if not base.startswith(("http://", "https://")):
                base = "https://" + base
            parts = urllib.parse.urlsplit(base)
            self.origin = f"{parts.scheme}://{parts.netloc}"
        self.delay = delay
        self.timeout = timeout
        self._last = 0.0
        self._robots = None
        self.requests = 0

    # ---- robots.txt ---------------------------------------------------------
    def allowed(self, url: str) -> bool:
        if self.local:
            return True
        if self._robots is None:
            self._robots = urllib.robotparser.RobotFileParser()
            r = self._get(self.origin + "/robots.txt")
            self._robots.parse(r.text.splitlines() if r.status == 200 else [])
        return self._robots.can_fetch(USER_AGENT, url)

    # ---- fetching -----------------------------------------------------------
    def url_for(self, path_or_url: str) -> str:
        if path_or_url.startswith(("http://", "https://")):
            return path_or_url
        return self.origin + ("" if path_or_url.startswith("/") else "/") + path_or_url

    def get(self, path_or_url: str) -> Response:
        url = self.url_for(path_or_url)
        if not self.local and not self.allowed(url):
            return Response(url, url, 0, "", "blocked by robots.txt")
        return self._get(url)

    def _get(self, url: str) -> Response:
        if self.local:
            return self._get_local(url)
        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        self.requests += 1
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return Response(url, resp.geturl(), resp.status, body)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            return Response(url, e.geturl() or url, e.code, body)
        except Exception as e:  # network errors: report, never crash the audit
            return Response(url, url, 0, "", str(e))

    def _get_local(self, url: str) -> Response:
        path = urllib.parse.urlsplit(url).path
        rel = path.strip("/")
        candidates = [self.local / rel] if rel.endswith(".xml") or rel == "robots.txt" else \
            [self.local / (rel + ".html") if rel else self.local / "index.html", self.local / rel / "index.html"]
        for c in candidates:
            if c.is_file():
                return Response(url, url, 200, c.read_text(encoding="utf-8"))
        return Response(url, url, 404, "")


# ---- sitemaps ---------------------------------------------------------------
def parse_sitemap(xml_text: str) -> tuple[str, list[dict]]:
    """Return ("index", [{loc}]) or ("urlset", [{loc, lastmod, alternates}])."""
    try:
        root = ET.fromstring(xml_text.strip().encode("utf-8"))
    except ET.ParseError:
        return "invalid", []
    tag = root.tag.replace(SM_NS, "")
    items = []
    if tag == "sitemapindex":
        for sm in root.findall(f"{SM_NS}sitemap"):
            loc = (sm.findtext(f"{SM_NS}loc") or "").strip()
            if loc:
                items.append({"loc": loc})
        return "index", items
    if tag == "urlset":
        for u in root.findall(f"{SM_NS}url"):
            loc = (u.findtext(f"{SM_NS}loc") or "").strip()
            if not loc:
                continue
            alternates = [a.get("href") for a in u
                          if a.tag.endswith("}link") and a.get("rel") == "alternate" and a.get("href")]
            items.append({"loc": loc, "lastmod": (u.findtext(f"{SM_NS}lastmod") or "").strip(),
                          "alternates": alternates})
        return "urlset", items
    return "invalid", []


def section_name(sitemap_url: str) -> str:
    """'pages-sitemap.xml' -> 'pages'; Wix dynamic sitemaps -> 'dynamic: team'."""
    name = urllib.parse.urlsplit(sitemap_url).path.rsplit("/", 1)[-1]
    name = name.removesuffix(".xml").removesuffix("-sitemap")
    if name.startswith("dynamic-"):
        return "dynamic: " + name[len("dynamic-"):].split("_p_")[0]
    return name or "sitemap"


def read_sitemaps(source: Source, notes: list[str]) -> list[dict]:
    """Every URL in the site's sitemap index, tagged with the section it came from."""
    r = source.get("/sitemap.xml")
    if r.status != 200:
        notes.append(f"sitemap.xml returned status {r.status or r.error}; only the home page was checked")
        return []
    kind, items = parse_sitemap(r.text)
    if kind == "invalid":
        notes.append("sitemap.xml is not a valid sitemap (the domain may not be connected); only the home page was checked")
        return []
    urls: list[dict] = []
    if kind == "urlset":
        return [{**i, "section": "pages"} for i in items]
    for sm in items:
        child = source.get(sm["loc"] if not source.local else urllib.parse.urlsplit(sm["loc"]).path)
        if child.status != 200:
            notes.append(f"{section_name(sm['loc'])} sitemap returned status {child.status or child.error}")
            continue
        _, entries = parse_sitemap(child.text)
        urls += [{**e, "section": section_name(sm["loc"])} for e in entries]
    return urls
