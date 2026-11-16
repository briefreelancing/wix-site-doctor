"""Match an old site's URLs to the new Wix site's pages and plan 301 redirects.

Matching, most certain first:
  same_path   the old path still exists on the new site: no redirect needed
  same_slug   the last part of the path is the same (WordPress /2024/05/sourdough/ and
              Squarespace /blog/sourdough both match Wix /post/sourdough)
  suggested   the best word-overlap match; needs a human decision before it is used
  none        nothing close; needs a human decision

Only same_slug matches go into the redirect file automatically.
"""

from __future__ import annotations

import re
import urllib.parse
from pathlib import Path

from .fetch import Source, parse_sitemap, read_sitemaps
from .fileio import read_tables

THRESHOLDS = {"suggest_min_overlap": 0.5, "wix_max_per_file": 500, "wix_max_per_site": 5000}
SKIP_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".css", ".js", ".ico", ".woff", ".woff2",
                 ".xml", ".txt", ".json")
SKIP_PARTS = ("/wp-content/", "/wp-includes/", "/wp-json/", "/feed", "/cdn-cgi/", "/static/")
STRIP_EXT = re.compile(r"\.(html?|php|aspx?)$", re.I)
STOP = {"a", "an", "the", "and", "or", "of", "for", "to", "in", "on", "with", "page", "html", "index"}
URL_HEADERS = {"address", "url", "page", "pages", "top pages", "landing page", "loc", "old url", "clicks",
               "impressions", "ctr", "position", "status code", "title 1", "title"}


def clean_path(u: str) -> str:
    """Path only, lower case, no trailing slash, no .html/.php ending, no index page."""
    p = urllib.parse.urlsplit(u.strip()).path if "://" in u else u.strip().split("?")[0].split("#")[0]
    p = urllib.parse.unquote(p).lower()
    p = re.sub(r"/index$", "", STRIP_EXT.sub("", p.rstrip("/")))
    return p or "/"


def last_slug(path: str) -> str:
    return path.rstrip("/").rsplit("/", 1)[-1]


def tokens(text: str) -> frozenset[str]:
    ws = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP and not re.fullmatch(r"\d{1,4}", w)]
    return frozenset(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in ws)


def skip_reason(path: str) -> str | None:
    if path.endswith(SKIP_SUFFIXES) or any(s in path + "/" for s in SKIP_PARTS):
        return "file or system URL"
    if re.search(r"/(page|tag|author)/", path + "/") or re.search(r"/page/\d+$", path):
        return "archive or pagination URL"
    return None


# ---- reading the old site's URLs ----------------------------------------------
def read_old_urls(inputs: list[str], notes: list[str]) -> list[dict]:
    """Old URLs from sitemap files, a live sitemap URL, a crawl or Search Console CSV, or a text list."""
    found: dict[str, dict] = {}

    def add(url: str, impressions=None, source=""):
        url = url.strip()
        if not url or url.startswith("#"):
            return
        path = clean_path(url)
        cur = found.setdefault(path, {"old_url": url, "path": path, "impressions": None, "source": source})
        if impressions is not None:
            cur["impressions"] = (cur["impressions"] or 0) + impressions

    for item in inputs:
        p = Path(item).expanduser()
        if item.startswith(("http://", "https://")):
            src = Source(item)
            if item.endswith(".xml"):
                r = src.get(item)
                kind, entries = parse_sitemap(r.text)
                if kind == "index":
                    for sm in entries:
                        _, e2 = parse_sitemap(src.get(sm["loc"]).text)
                        for e in e2:
                            add(e["loc"], source="old sitemap")
                else:
                    for e in entries:
                        add(e["loc"], source="old sitemap")
            else:
                for e in read_sitemaps(src, notes):
                    add(e["loc"], source="old sitemap")
        elif p.is_file() and p.suffix.lower() == ".xml":
            kind, entries = parse_sitemap(p.read_text(encoding="utf-8"))
            if kind == "index":
                notes.append(f"{p.name} is a sitemap index; upload the sitemaps it lists, or give the live URL")
            for e in entries if kind == "urlset" else []:
                add(e["loc"], source=p.name)
        elif p.is_file() and p.suffix.lower() == ".txt":
            for line in p.read_text(encoding="utf-8").splitlines():
                add(line, source=p.name)
        elif p.exists():
            tables, problems = read_tables([p], URL_HEADERS)
            notes.extend(problems)
            for t in tables:
                col = next((c for c in ("address", "url", "page", "top pages", "pages", "landing page", "loc", "old url")
                            if c in t.headers), None)
                if not col:
                    notes.append(f"{t.name}: no URL column found. Columns seen: {', '.join(t.headers[:8])}")
                    continue
                imp_col = "impressions" if "impressions" in t.headers else None
                status = "status code" if "status code" in t.headers else None
                for row in t.rows:
                    if status and row.get(status, "").strip()[:1] in ("3", "4", "5"):
                        continue
                    imp = None
                    if imp_col:
                        try:
                            imp = float(row.get(imp_col, "").replace(",", "") or 0)
                        except ValueError:
                            imp = None
                    add(row.get(col, ""), imp, t.name)
        else:
            raise FileNotFoundError(f"Not found: {item}")
    return list(found.values())


# ---- matching -------------------------------------------------------------------
def plan(old: list[dict], new_pages: list[dict]) -> dict:
    """new_pages: [{url, title?}] for every live page on the new Wix site."""
    T = THRESHOLDS
    new_by_path = {}
    for n in new_pages:
        new_by_path.setdefault(clean_path(n["url"]), n)
    by_slug: dict[str, list[str]] = {}
    for path in new_by_path:
        by_slug.setdefault(last_slug(path), []).append(path)
    new_tokens = {path: tokens(path.replace("/", " ") + " " + (new_by_path[path].get("title") or "").split(" | ")[0])
                  for path in new_by_path}

    rows, skipped = [], []
    for o in sorted(old, key=lambda x: (-(x["impressions"] or 0), x["path"])):
        path = o["path"]
        why = skip_reason(path)
        if why:
            skipped.append({**o, "reason": why})
            continue
        row = {**o, "match": "none", "new_path": "", "candidates": [], "overlap": None}
        if path in new_by_path:
            row.update(match="same_path", new_path=path)
        elif path != "/" and len(by_slug.get(last_slug(path), [])) == 1:
            row.update(match="same_slug", new_path=by_slug[last_slug(path)][0])
        else:
            ot = tokens(path.replace("/", " "))
            scored = sorted(((len(ot & nt) / len(ot | nt) if ot | nt else 0.0, np) for np, nt in new_tokens.items()),
                            key=lambda x: (-x[0], x[1]))
            row["candidates"] = [np for s, np in scored[:3] if s > 0]
            if scored and scored[0][0] >= T["suggest_min_overlap"] and \
                    (len(scored) == 1 or scored[0][0] > scored[1][0]):
                row.update(match="suggested", new_path=scored[0][1], overlap=round(scored[0][0], 2))
        rows.append(row)
    counts = {k: sum(1 for r in rows if r["match"] == k) for k in ("same_path", "same_slug", "suggested", "none")}
    return {
        "totals": {"old_urls": len(old), "skipped": len(skipped), **counts,
                   "new_pages": len(new_by_path)},
        "rows": rows,
        "skipped": skipped,
        "new_paths": sorted(new_by_path),
        "thresholds": T,
    }
