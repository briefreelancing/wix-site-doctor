"""Gatekeeper: nothing is rendered until the written work agrees with the audit.

Errors block the render. Warnings are shown but do not block.
"""

from __future__ import annotations

import re
import urllib.parse

from .audit import alt_looks_like_file_name, norm_url
from .migrate import clean_path

ALT_FILLER = re.compile(r"^(an? )?(image|picture|photo|graphic) of\b", re.I)
ALT_BASIS = {"seen", "owner description", "file name"}


def _numbers_in(obj) -> set[float]:
    found: set[float] = set()
    if isinstance(obj, bool):
        return found
    if isinstance(obj, (int, float)):
        found.add(round(float(obj), 1))
    elif isinstance(obj, dict):
        for v in obj.values():
            found |= _numbers_in(v)
    elif isinstance(obj, list):
        for v in obj:
            found |= _numbers_in(v)
    return found


def untraceable_numbers(text: str, allowed: set[float]) -> list[str]:
    cleaned = re.sub(r"https?://\S+|(?<!\w)/[\w\-./]+", " ", str(text or ""))  # URLs and paths like /about-5
    bad = []
    for raw in re.findall(r"(?<![\w.])\d[\d,]*(?:\.\d+)?", cleaned):
        try:
            value = round(float(raw.replace(",", "")), 1)
        except ValueError:
            continue
        if value not in allowed:
            bad.append(raw)
    return bad


def check_fixes(audit: dict, fixes: dict) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    T = audit["thresholds"]
    pages = {norm_url(p["url"]): p for p in audit["pages"] if p["status"] == 200}
    site = audit["site"]["site_name"]
    items = fixes.get("pages", [])
    alts = fixes.get("alt_text", [])
    if not items and not alts:
        errors.append("no fixes found: fill 'pages', 'alt_text', or both")
    rewritten = {norm_url(f.get("url", "")) for f in items if f.get("new_title")}
    kept_titles = {p["title"].lower() for k, p in pages.items() if k not in rewritten and p["title"]}
    redesc = {norm_url(f.get("url", "")) for f in items if f.get("new_description")}
    kept_descs = {p["description"].lower() for k, p in pages.items() if k not in redesc and p["description"]}
    suffix_share = sum(1 for p in pages.values() if site and p["title"].endswith(" | " + site))
    uses_suffix = site and suffix_share * 2 >= len(pages)
    new_titles: dict[str, str] = {}
    new_descs: dict[str, str] = {}
    for f in items:
        url = f.get("url", "")
        p = pages.get(norm_url(url))
        if p is None:
            errors.append(f"{url}: not a page that loaded in the audit")
            continue
        title = str(f.get("new_title", "")).strip()
        desc = str(f.get("new_description", "")).strip()
        if not str(f.get("reason", "")).strip():
            errors.append(f"{url}: add a reason so the reviewer knows why the change is proposed")
        if not title and not desc:
            errors.append(f"{url}: give a new_title, a new_description, or both")
        if title:
            if len(title) > T["title_max_chars"]:
                errors.append(f"{url}: new title is {len(title)} characters; the limit is {T['title_max_chars']}")
            elif len(title) < T["title_min_chars"]:
                warnings.append(f"{url}: new title is {len(title)} characters; aim for at least {T['title_min_chars']}")
            if title.lower() in kept_titles or title.lower() in new_titles:
                errors.append(f"{url}: new title is already used by another page")
            new_titles[title.lower()] = url
            if uses_suffix and not title.endswith(" | " + site):
                warnings.append(f"{url}: most titles end with ' | {site}'; this one does not")
            if title == p["title"]:
                warnings.append(f"{url}: new title is the same as the current one")
        if desc:
            if len(desc) > T["description_max_chars"]:
                errors.append(f"{url}: new description is {len(desc)} characters; the limit is {T['description_max_chars']}")
            elif len(desc) < T["description_min_chars"]:
                errors.append(f"{url}: new description is {len(desc)} characters; Wix recommends at least "
                              f"{T['description_min_chars']}")
            if desc.lower() in kept_descs or desc.lower() in new_descs:
                errors.append(f"{url}: new description is already used by another page")
            new_descs[desc.lower()] = url
        elif "description_missing" in p["issues"]:
            warnings.append(f"{url}: the page has no description and none was written")
    per_page: dict[str, set[str]] = {}
    shared = {i["image"]: i for i in audit.get("shared_images", [])}
    for a in alts:
        url, key = a.get("url", ""), a.get("image", "")
        p = pages.get(norm_url(url))
        if p is None:
            errors.append(f"{url}: not a page that loaded in the audit")
            continue
        img = next((i for i in p["image_fixes"] if i["image"] == key), None) or shared.get(key)
        if img is None:
            errors.append(f"{url}: image '{key}' is not one of this page's flagged images or a site-wide image")
            continue
        alt = str(a.get("new_alt", "")).strip()
        basis = str(a.get("basis", "")).strip()
        if basis not in ALT_BASIS:
            errors.append(f"{url} {img['file']}: set basis to one of {', '.join(sorted(ALT_BASIS))} "
                          "(alt text must come from seeing the image, the owner's description, or a clear file name)")
        elif basis == "file name" and alt:
            warnings.append(f"{url} {img['file']}: alt text written from the file name only; the reviewer should look "
                            "at the image")
        if not alt:
            if not a.get("decorative"):
                errors.append(f"{url} {img['file']}: new_alt is empty (set decorative: true if the image is decorative)")
            continue
        if len(alt) > T["alt_max_chars"]:
            errors.append(f"{url} {img['file']}: alt text is {len(alt)} characters; keep it under {T['alt_max_chars']}")
        if alt_looks_like_file_name(alt, img["file"]):
            errors.append(f"{url} {img['file']}: the new alt text still looks like a file name")
        if ALT_FILLER.search(alt):
            warnings.append(f"{url} {img['file']}: drop 'image of' or 'picture of'; Wix advises against it")
        seen = per_page.setdefault(norm_url(url), set())
        if alt.lower() in seen:
            warnings.append(f"{url} {img['file']}: same alt text as another image on this page; Wix advises "
                            "unique alt text per page")
        seen.add(alt.lower())
    return errors, warnings


def check_summary(audit: dict, summary: dict, fixes: dict | None = None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    allowed = (_numbers_in(audit["totals"]) | _numbers_in(audit["sections"]) | _numbers_in(audit["thresholds"])
               | {float(len(audit["site_issues"])), float(len(audit["rewrite_queue"]))})
    if fixes:
        allowed |= {float(len(fixes.get("pages", []))), float(len(fixes.get("alt_text", [])))}
    texts = [("headline", summary.get("headline", ""))]
    texts += [(f"summary[{i}]", t) for i, t in enumerate(summary.get("summary", []))]
    texts += [(f"next_steps[{i}]", t) for i, t in enumerate(summary.get("next_steps", []))]
    if not summary.get("headline"):
        errors.append("summary.json needs a headline")
    for field, text in texts:
        for raw in untraceable_numbers(text, allowed):
            errors.append(f"the number {raw} in {field} is not in audit.json totals")
    return errors, []


def resolve_redirects(plan: dict, decisions: dict | None) -> tuple[list[dict], list[dict], list[str], list[str]]:
    """Return (redirects, unresolved, errors, warnings)."""
    errors, warnings = [], []
    decisions = decisions or {}
    T = plan["thresholds"]
    rows = {r["path"]: r for r in plan["rows"]}
    new_paths = set(plan["new_paths"])
    approved = {clean_path(p) for p in decisions.get("approve_suggested", [])}
    custom = {clean_path(d.get("old", "")): d for d in decisions.get("set", [])}
    skipped = {clean_path(d.get("old", "")) for d in decisions.get("skip", [])}
    for old in approved | set(custom) | skipped:
        if old not in rows:
            errors.append(f"{old}: not an old URL in redirect_plan.json")
    for old in approved:
        if old in rows and rows[old]["match"] != "suggested":
            errors.append(f"{old}: approve_suggested only applies to suggested matches; use 'set' instead")
    redirects, unresolved = [], []
    for path, r in rows.items():
        if r["match"] == "same_path" or path in skipped:
            continue
        target, how = None, ""
        if path in custom:
            target, how = str(custom[path].get("new", "")).strip(), "set by reviewer"
            if not str(custom[path].get("reason", "")).strip():
                warnings.append(f"{path}: add a reason for the chosen target")
        elif r["match"] == "same_slug":
            target, how = r["new_path"], "same page name"
        elif r["match"] == "suggested" and path in approved:
            target, how = r["new_path"], "suggested match, approved"
        if target is None:
            unresolved.append(r)
            continue
        old_src = urllib.parse.urlsplit(r["old_url"]).path if "://" in r["old_url"] else r["old_url"]
        old_src = old_src.split("?")[0] or "/"
        redirects.append({"old": old_src, "new": target, "how": how, "old_key": path})
    seen = set()
    olds = {r["old_key"] for r in redirects}
    for r in redirects:
        new = r["new"]
        if r["old_key"] == "/":
            errors.append("/: the home page cannot be redirected")
        if r["old_key"] in seen:
            errors.append(f"{r['old']}: listed twice")
        seen.add(r["old_key"])
        if "?lang=" in new:
            errors.append(f"{r['old']}: Wix does not accept ?lang= in a redirect target")
        if new.startswith(("http://", "https://")):
            warnings.append(f"{r['old']}: points to an external URL ({new}); check that is intended")
        else:
            np = clean_path(new)
            if np not in new_paths:
                errors.append(f"{r['old']}: target {new} is not a page on the new site")
            elif np == r["old_key"]:
                errors.append(f"{r['old']}: redirects to itself")
            elif np in olds:
                errors.append(f"{r['old']}: target {new} is itself being redirected (a redirect chain)")
            r["new"] = np
    if len(redirects) > T["wix_max_per_site"]:
        errors.append(f"{len(redirects)} redirects; Wix allows at most {T['wix_max_per_site']} per site")
    if unresolved:
        warnings.append(f"{len(unresolved)} old URL(s) have no target yet; they are listed in redirects_review.csv")
    return redirects, unresolved, errors, warnings
