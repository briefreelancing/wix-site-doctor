#!/usr/bin/env python3
"""Wix Site Doctor command line.

    wixdoctor.py audit <site URL or local mirror folder> --out wix_out [--gsc pages.csv] [--max-pages 150]
    wixdoctor.py check --out wix_out              check fixes.json and summary.json without rendering
    wixdoctor.py render --out wix_out             client report (+ fix sheet when fixes.json exists)
    wixdoctor.py migrate --old <old URLs...> --new <new Wix site> --out wix_out
    wixdoctor.py render-redirects --out wix_out   redirect files for Wix's URL Redirect Manager

Only public pages are read, one at a time, with a pause between requests, and robots.txt
is respected. Nothing on the site is changed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from doctor_core import audit, check, migrate, render  # noqa: E402
from doctor_core.fetch import Source, read_sitemaps  # noqa: E402
from doctor_core.fileio import read_tables  # noqa: E402


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _read(path: Path, what: str, required: bool = True) -> dict | None:
    if not path.exists():
        if required:
            sys.exit(f"Missing {path}. {what}")
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _report(errors: list[str], warnings: list[str]) -> int:
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


def _gsc_impressions(path: str, notes: list[str]) -> dict[str, float]:
    tables, problems = read_tables([path], {"page", "pages", "top pages", "url", "landing page", "clicks",
                                            "impressions", "ctr", "position"})
    notes.extend(problems)
    found: dict[str, float] = {}
    for t in tables:
        col = next((c for c in ("top pages", "pages", "page", "url", "landing page") if c in t.headers), None)
        if not col or "impressions" not in t.headers:
            notes.append(f"{t.name}: not a Search Console pages export (needs a page column and impressions)")
            continue
        for row in t.rows:
            try:
                found[audit.norm_url(row[col])] = float(row["impressions"].replace(",", "") or 0)
            except (KeyError, ValueError):
                continue
    return found


def cmd_audit(a) -> int:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []
    src = Source(a.site, delay=a.delay)
    pages, sections = audit.crawl(src, a.max_pages, notes)
    imps = _gsc_impressions(a.gsc, notes) if a.gsc else {}
    origin = src.origin
    if src.local and pages:  # a local mirror: report the site's own address from its sitemap
        origin = "/".join(pages[0]["url"].split("/")[:3])
    result = audit.build(pages, sections, origin, imps, notes, a.max_pages)
    result["client"] = a.client or ""
    _write(out / "audit.json", result)
    t = result["totals"]
    print(json.dumps({"site": result["site"], "sections": result["sections"], "totals": t,
                      "site_issues": [s["code"] for s in result["site_issues"]], "notes": result["notes"],
                      "requests_made": src.requests}, indent=2, ensure_ascii=False))
    return 0 if t["pages_loaded"] else 1


def _checks(out: Path):
    result = _read(out / "audit.json", "Run audit first.")
    fixes = _read(out / "fixes.json", "", required=False)
    summary = _read(out / "summary.json", "Write summary.json from templates/summary_template.json first.")
    errors, warnings = check.check_summary(result, summary, fixes)
    if fixes:
        e2, w2 = check.check_fixes(result, fixes)
        errors, warnings = errors + e2, warnings + w2
    return result, fixes, summary, errors, warnings


def cmd_check(a) -> int:
    *_, errors, warnings = _checks(Path(a.out))
    return _report(errors, warnings)


def cmd_render(a) -> int:
    out = Path(a.out)
    result, fixes, summary, errors, warnings = _checks(out)
    if _report(errors, warnings):
        print("Not rendered. Fix the errors above, then run again.")
        return 1
    paths = [render.render_report(result, summary, fixes, out)]
    if fixes:
        paths += render.render_fixes(result, fixes, out)
        if not any(str(p).endswith(".xlsx") for p in paths):
            print("openpyxl is not installed, so the fix sheet was written as CSV only (pip install openpyxl)")
    for p in paths:
        print(f"wrote {p}")
    return 0


def cmd_migrate(a) -> int:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []
    old = migrate.read_old_urls(a.old, notes)
    titles = {}
    existing = _read(out / "audit.json", "", required=False)
    if existing:
        titles = {audit.norm_url(p["url"]): p["title"] for p in existing["pages"]}
    src = Source(a.new, delay=a.delay)
    new_urls = read_sitemaps(src, notes)
    if not new_urls:
        notes.append("the new site's sitemap listed no pages, so nothing could be matched")
    new_pages = [{"url": u["loc"], "title": titles.get(audit.norm_url(u["loc"]), "")} for u in new_urls]
    result = migrate.plan(old, new_pages)
    result["notes"] = notes
    _write(out / "redirect_plan.json", result)
    print(json.dumps({"totals": result["totals"], "notes": notes}, indent=2))
    return 0


def cmd_render_redirects(a) -> int:
    out = Path(a.out)
    plan = _read(out / "redirect_plan.json", "Run migrate first.")
    decisions = _read(out / "redirect_decisions.json", "", required=False)
    redirects, unresolved, errors, warnings = check.resolve_redirects(plan, decisions)
    if _report(errors, warnings):
        print("Not rendered. Fix the errors above, then run again.")
        return 1
    for p in render.render_redirects(redirects, unresolved, out, plan["thresholds"]["wix_max_per_file"]):
        print(f"wrote {p}")
    print(f"{len(redirects)} redirect(s) ready to import; {len(unresolved)} old URL(s) still need a decision")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="wixdoctor", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    au = sub.add_parser("audit", help="read the site and run every check")
    au.add_argument("site", help="site URL (https://www.example.com) or a local mirror folder")
    au.add_argument("--out", default="wix_out")
    au.add_argument("--client", default="")
    au.add_argument("--gsc", help="Search Console pages export (CSV or zip) to order pages by impressions")
    au.add_argument("--max-pages", type=int, default=audit.THRESHOLDS["max_pages"])
    au.add_argument("--delay", type=float, default=1.0, help="seconds between requests (default 1)")
    au.set_defaults(fn=cmd_audit)
    mi = sub.add_parser("migrate", help="match old URLs to the new Wix site")
    mi.add_argument("--old", nargs="+", required=True,
                    help="old sitemap.xml (file or URL), crawl or Search Console CSV, or a .txt list of URLs")
    mi.add_argument("--new", required=True, help="the new Wix site's URL or a local mirror folder")
    mi.add_argument("--out", default="wix_out")
    mi.add_argument("--delay", type=float, default=1.0)
    mi.set_defaults(fn=cmd_migrate)
    for name, fn in [("check", cmd_check), ("render", cmd_render), ("render-redirects", cmd_render_redirects)]:
        p = sub.add_parser(name)
        p.add_argument("--out", default="wix_out")
        p.set_defaults(fn=fn)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
