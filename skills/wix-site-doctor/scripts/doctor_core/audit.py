"""Audit a Wix site from its sitemap and page HTML.

Every check is a fact read from the page or a rule written down in THRESHOLDS, so a
reader can question it. Length limits follow Wix's own Help Center guidance (titles
under 60 characters, descriptions 50 to 160); the rest are rules of thumb.
"""

from __future__ import annotations

import re
import urllib.parse
from collections import Counter

from . import page as pagemod
from .fetch import Source, read_sitemaps

THRESHOLDS = {
    "title_max_chars": 60,
    "title_min_chars": 30,
    "description_min_chars": 50,
    "description_max_chars": 160,
    "alt_max_chars": 125,
    "max_pages": 150,
    "default_title_max_words": 3,
}
GENERIC_PAGE_NAMES = {
    "home", "about", "about us", "contact", "contact us", "services", "shop", "store", "blog", "gallery",
    "portfolio", "faq", "faqs", "team", "menu", "events", "book online", "pricing", "products", "work",
    "new page", "blank", "page", "projects", "reviews", "testimonials", "news", "resources", "plans",
}
SECTION_ORDER = ["pages", "blog-posts", "store-products", "store-categories", "blog-categories"]

ISSUE_TEXT = {
    "page_error": "Page did not load (error status)",
    "redirected": "Sitemap URL redirects somewhere else",
    "noindex_in_sitemap": "Page is in the sitemap but tells search engines not to index it",
    "canonical_elsewhere": "Canonical tag points to a different URL",
    "title_missing": "No title",
    "title_too_long": "Title is likely to be cut off in search results",
    "title_too_short": "Title is short and may undersell the page",
    "title_looks_default": "Title is Wix's default 'Page name | Site name', or a leftover 'Copy of' name",
    "home_title_default": "Home page title is only the site name (Wix's default)",
    "title_duplicate": "Same title as another page",
    "description_missing": "No meta description (Wix leaves it blank by default)",
    "description_too_short": "Description is short",
    "description_too_long": "Description is likely to be cut off",
    "description_duplicate": "Same description as another page",
    "h1_missing": "No H1 heading",
    "h1_multiple": "More than one H1 heading",
    "url_copy_of": "URL starts with 'copy-of', left from a duplicated page",
    "url_blank": "URL is a placeholder name such as 'blank' or 'new-page'",
    "url_auto_numbered": "URL looks auto-numbered (for example /about-5)",
    "alt_is_file_name": "Image alt text is the uploaded file name",
    "alt_empty": "Image has empty alt text (fine only if it is decorative)",
    "social_image_missing": "No social share image",
}
WEIGHT = {"page_error": 5, "noindex_in_sitemap": 4, "title_missing": 4, "redirected": 3, "canonical_elsewhere": 3,
          "description_missing": 3, "title_looks_default": 3, "home_title_default": 3, "title_duplicate": 3,
          "url_copy_of": 3, "url_blank": 3, "alt_is_file_name": 2, "description_duplicate": 2,
          "title_too_long": 2, "h1_missing": 2, "url_auto_numbered": 1, "title_too_short": 1,
          "description_too_short": 1, "description_too_long": 1, "h1_multiple": 1, "alt_empty": 1,
          "social_image_missing": 1}
FILE_NAME_ALT = re.compile(
    r"(\.(jpe?g|png|gif|webp|svg|heic|avif|tiff?)$)|^(img|dsc|dscn|dcim|pxl|screenshot|untitled|image|photo|file)"
    r"([\s_-]*\d.*)?$|^[\w-]*\d{4,}[\w-]*$|[_~]mv2", re.I)


def words(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", str(text or "").lower())


def norm_url(u: str) -> str:
    u = re.sub(r"#.*$", "", str(u or "").strip())
    u = re.sub(r"^https?://", "", u, flags=re.I)
    u = re.sub(r"^www\.", "", u, flags=re.I)
    return u.rstrip("/").lower()


def path_of(u: str) -> str:
    return urllib.parse.urlsplit(u).path.rstrip("/") or "/"


def alt_looks_like_file_name(alt: str, file: str) -> bool:
    a = alt.strip()
    if not a:
        return False
    stem = re.sub(r"\.\w+$", "", file)
    return bool(FILE_NAME_ALT.search(a)) or (len(stem) >= 2 and a.lower() == stem.lower())


def slug_issue(path: str) -> str | None:
    seg = path.rstrip("/").rsplit("/", 1)[-1].lower()
    if not seg:
        return None
    if seg.startswith("copy-of-"):
        return "url_copy_of"
    if re.fullmatch(r"(blank|new-page|untitled|page)(-\d+)?", seg):
        return "url_blank"
    if re.fullmatch(r"[a-z]+(-[a-z]+)?-\d{1,2}", seg):
        return "url_auto_numbered"
    return None


def site_name_from(pages: list[dict]) -> str:
    named = Counter(p["og_site_name"] for p in pages if p.get("og_site_name"))
    if named:
        return named.most_common(1)[0][0]
    suffixes = Counter(p["title"].rsplit(" | ", 1)[1] for p in pages if " | " in p.get("title", ""))
    return suffixes.most_common(1)[0][0] if suffixes else ""


def _order(urls: list[dict]) -> list[dict]:
    rank = {s: i for i, s in enumerate(SECTION_ORDER)}
    return sorted(urls, key=lambda u: (path_of(u["loc"]) != "/", rank.get(u["section"], len(rank)), u["loc"]))


def crawl(source: Source, max_pages: int, notes: list[str]) -> tuple[list[dict], dict]:
    sitemap_urls = read_sitemaps(source, notes)
    sections = dict(Counter(u["section"] for u in sitemap_urls))
    if not any(path_of(u["loc"]) == "/" for u in sitemap_urls):
        sitemap_urls.append({"loc": source.url_for("/"), "section": "home (not in sitemap)", "lastmod": ""})
    todo = _order(sitemap_urls)
    if len(todo) > max_pages:
        notes.append(f"the sitemap lists {len(todo)} URLs; the first {max_pages} were checked "
                     "(static pages first, then blog posts, then store pages). Raise --max-pages to check more")
        todo = todo[:max_pages]
    pages = []
    for u in todo:
        r = source.get(u["loc"])
        info = pagemod.parse(r.text) if r.text else pagemod.parse("")
        pages.append({"url": u["loc"], "section": u["section"], "status": r.status, "error": r.error,
                      "final_url": r.final_url, **info})
    return pages, sections


def build(pages: list[dict], sections: dict, origin: str, impressions: dict[str, float] | None = None,
          notes: list[str] | None = None, max_pages: int | None = None) -> dict:
    T = THRESHOLDS
    notes = list(notes or [])
    impressions = impressions or {}
    ok = [p for p in pages if p["status"] == 200 and not p["is_connect_domain_error"]]
    site = site_name_from(ok)
    title_counts = Counter(p["title"].lower() for p in ok if p["title"])
    desc_counts = Counter(p["description"].lower() for p in ok if p["description"])
    any_social = any(p["og_image"] for p in ok)
    # Images on most pages sit in the header or footer: report them once, as site-wide.
    image_pages = Counter(i["image"] for p in ok for i in p["images"])
    shared_min = max(3, (len(ok) + 1) // 2)
    shared = {k for k, n in image_pages.items() if n >= shared_min}
    shared_fixes: dict[str, dict] = {}

    out_pages = []
    for p in pages:
        issues: list[str] = []
        alt_fixes: list[dict] = []
        path = path_of(p["url"])
        if p["status"] != 200 or p["is_connect_domain_error"]:
            issues.append("page_error")
        else:
            if norm_url(p["final_url"]) != norm_url(p["url"]):
                issues.append("redirected")
            if "noindex" in p["robots"]:
                issues.append("noindex_in_sitemap")
            if p["canonical"] and norm_url(p["canonical"]) != norm_url(p["final_url"]):
                issues.append("canonical_elsewhere")
            t = p["title"]
            if not t:
                issues.append("title_missing")
            else:
                default = None
                if path == "/" and site and t.strip().lower() == site.lower():
                    default = "home_title_default"
                elif t.lower().startswith("copy of "):
                    default = "title_looks_default"
                elif site and t.endswith(" | " + site) and p["section"] in ("pages", "home (not in sitemap)"):
                    name = t[: -len(" | " + site)].strip()
                    slug_words = set(words(path))
                    if (len(words(name)) <= T["default_title_max_words"]
                            and (name.lower() in GENERIC_PAGE_NAMES or (slug_words and set(words(name)) <= slug_words))):
                        default = "title_looks_default"
                if len(t) > T["title_max_chars"]:
                    issues.append("title_too_long")
                elif len(t) < T["title_min_chars"] and not default:
                    issues.append("title_too_short")
                if default:
                    issues.append(default)
                if title_counts[t.lower()] > 1:
                    issues.append("title_duplicate")
            d = p["description"]
            if not d:
                issues.append("description_missing")
            else:
                if len(d) > T["description_max_chars"]:
                    issues.append("description_too_long")
                elif len(d) < T["description_min_chars"]:
                    issues.append("description_too_short")
                if desc_counts[d.lower()] > 1:
                    issues.append("description_duplicate")
            if not p["h1"]:
                issues.append("h1_missing")
            elif len(p["h1"]) > 1:
                issues.append("h1_multiple")
            if p["section"] in ("pages", "home (not in sitemap)"):
                s = slug_issue(path)
                if s:
                    issues.append(s)
            for img in p["images"]:
                if img["alt"] and alt_looks_like_file_name(img["alt"], img["file"]):
                    fix = {**img, "issue": "alt_is_file_name"}
                elif img["has_alt"] and not img["alt"]:
                    fix = {**img, "issue": "alt_empty"}
                else:
                    continue
                if img["image"] in shared:
                    shared_fixes.setdefault(img["image"], {**fix, "url": p["url"], "pages": image_pages[img["image"]]})
                else:
                    alt_fixes.append(fix)
            if any(a["issue"] == "alt_is_file_name" for a in alt_fixes):
                issues.append("alt_is_file_name")
            if any(a["issue"] == "alt_empty" for a in alt_fixes):
                issues.append("alt_empty")
            if any_social and not p["og_image"]:
                issues.append("social_image_missing")
        imp = impressions.get(norm_url(p["url"]))
        out_pages.append({
            "url": p["url"], "path": path, "section": p["section"], "status": p["status"],
            "title": p["title"], "title_chars": len(p["title"]), "description": p["description"],
            "description_chars": len(p["description"]), "h1": p["h1"][:3], "canonical": p["canonical"],
            "images_checked": len(p["images"]), "image_fixes": alt_fixes,
            "issues": issues, "issue_text": [ISSUE_TEXT[i] for i in issues],
            "impressions": imp, "score": sum(WEIGHT[i] for i in issues),
        })

    # ---- site-level findings ----------------------------------------------------
    site_issues = []
    home = next((p for p in pages if path_of(p["url"]) == "/"), pages[0] if pages else None)
    host = urllib.parse.urlsplit(origin).netloc.lower()
    if home and home["is_connect_domain_error"]:
        site_issues.append({"code": "domain_not_connected",
                            "text": "The domain shows Wix's 'Connect Your Domain' error page instead of the site"})
    if host.endswith("wixsite.com"):
        site_issues.append({"code": "free_wix_url",
                            "text": "The site uses a free wixsite.com address; 301 redirects and a custom favicon need a connected domain"})
    if ok and all(pagemod.WIX_DEFAULT_FAVICON in p["favicon"] for p in ok):
        site_issues.append({"code": "default_favicon", "text": "The site still uses Wix's default favicon"})
    if ok and not any_social:
        site_issues.append({"code": "no_social_image",
                            "text": "No page has a social share image, so links shared on social media show no picture"})
    if ok and not any(p["is_wix"] for p in ok):
        site_issues.append({"code": "not_wix",
                            "text": "These pages do not identify as a Wix site; Wix-specific advice may not apply"})
    shared_bad = [f for f in shared_fixes.values() if f["issue"] == "alt_is_file_name"]
    if shared_bad:
        site_issues.append({"code": "shared_alt_is_file_name",
                            "text": f"{len(shared_bad)} image(s) in the header or footer, shown on most pages, "
                                    "have the uploaded file name as alt text"})
    langs = sorted({p["lang"] for p in ok if p["lang"]})
    multilingual = any(len({h.lower() for h in p["hreflang"] if h.lower() != "x-default"}) >= 2 for p in ok)
    if multilingual:
        notes.append("the site is multilingual; each language has its own redirects and SEO settings in Wix, "
                     "and redirects only work between pages in the same language")

    flagged = [p for p in out_pages if p["issues"]]
    flagged.sort(key=lambda p: (-(p["impressions"] or 0), p["path"] != "/", -p["score"], p["path"]))
    alt_queue = ([{**f, "site_wide": True} for f in shared_bad]
                 + [{"url": p["url"], **f, "site_wide": False} for p in flagged for f in p["image_fixes"]
                    if f["issue"] == "alt_is_file_name"])
    images_checked = len(image_pages)
    if not impressions:
        notes.append("no Search Console pages export, so pages are ordered by home page first, then by how serious "
                     "their issues are, not by traffic")
    return {
        "site": {"origin": origin, "site_name": site, "is_wix": any(p["is_wix"] for p in ok),
                 "languages": langs, "multilingual": multilingual},
        "sections": sections,
        "totals": {
            "urls_in_sitemap": sum(sections.values()),
            "pages_checked": len(out_pages),
            "pages_loaded": len(ok),
            "pages_with_issues": len(flagged),
            "issue_counts": dict(Counter(i for p in out_pages for i in p["issues"]).most_common()),
            "images_checked": images_checked,
            "images_alt_file_name": len({f["image"] for f in alt_queue}),
            "images_alt_file_name_site_wide": len(shared_bad),
            "images_alt_empty": len({f["image"] for p in out_pages for f in p["image_fixes"] if f["issue"] == "alt_empty"}
                                    | {f["image"] for f in shared_fixes.values() if f["issue"] == "alt_empty"}),
            "pages_matched_to_search_console": sum(1 for p in out_pages if p["impressions"] is not None),
        },
        "site_issues": site_issues,
        "shared_images": list(shared_fixes.values()),
        "rewrite_queue": [p["url"] for p in flagged],
        "alt_queue": alt_queue,
        "pages": out_pages,
        "site_urls": [p["url"] for p in out_pages if p["status"] == 200],
        "thresholds": dict(T, max_pages=max_pages or T["max_pages"]),
        "notes": notes,
    }
