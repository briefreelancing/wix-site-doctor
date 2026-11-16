"""Turn checked work into files people can use: a client report, a fix sheet and Wix redirect files."""

from __future__ import annotations

import csv
import html
from pathlib import Path

from .audit import ISSUE_TEXT, norm_url

HELP = "https://support.wix.com/en/article/"
# Where each problem is fixed in Wix, from the Wix Help Center. Menu names change; the links stay current.
FIX_GUIDE = {
    "title": ("Editor: Pages & Menu, the page's More Actions, Settings, then the SEO tab. Blog posts and store "
              "products have their own SEO settings.", HELP + "adding-seo-title-tags-and-meta-descriptions-to-your-pages"),
    "description": ("Same place as the title: the page's SEO settings.",
                    HELP + "adding-seo-title-tags-and-meta-descriptions-to-your-pages"),
    "alt": ("Editor: click the image, Settings, then 'What's in the image?'. For a Pro Gallery: Manage Media, "
            "select the image, Alt text.", HELP + "accessibility-preparing-your-images-and-galleries"),
    "url": ("Change the page URL in its SEO settings. Wix adds a 301 redirect automatically for editor pages, "
            "but not for blog posts: add those in the URL Redirect Manager.",
            HELP + "setting-up-a-301-redirect-for-a-page-on-your-site"),
    "social": ("The page's Social share settings, or one default social image for the whole site in SEO settings.",
               HELP + "understanding-your-sites-default-seo-settings-6447365"),
    "favicon": ("Dashboard: Settings, Website settings, Favicon. Needs a Premium plan and a connected domain.",
                HELP + "wix-editor-changing-your-favicon"),
    "redirects": ("Dashboard: SEO & GEO, Tools and settings, URL Redirect Manager, More Actions, Import redirects. "
                  "Up to 500 per file, 5,000 per site.", HELP + "importing-or-exporting-url-redirects-with-a-csv-file"),
    "index": ("The page's SEO settings: the option that lets search engines index the page.",
              HELP + "understanding-your-sites-default-seo-settings-6447365"),
    "h1": ("Editor: set the page's main heading text to Heading 1, and other headings to Heading 2 or lower.", ""),
}
GUIDE_FOR = {
    "title_missing": "title", "title_too_long": "title", "title_too_short": "title", "title_looks_default": "title",
    "home_title_default": "title", "title_duplicate": "title", "description_missing": "description",
    "description_too_short": "description", "description_too_long": "description",
    "description_duplicate": "description", "alt_is_file_name": "alt", "alt_empty": "alt", "url_copy_of": "url",
    "url_blank": "url", "url_auto_numbered": "url", "social_image_missing": "social", "noindex_in_sitemap": "index",
    "canonical_elsewhere": "index", "h1_missing": "h1", "h1_multiple": "h1", "page_error": "", "redirected": "",
    "default_favicon": "favicon", "no_social_image": "social", "free_wix_url": "redirects",
    "domain_not_connected": "", "not_wix": "", "shared_alt_is_file_name": "alt",
}

CSS = """
:root{--primary:#C1FF72;--primary-t40:#DBFFB5;--primary-s40:#5F8036;--accent-t60:#FFD1EF;--accent-s50:#632E54;
--neutral:#DAE1D4;--neutral-t60:#F0F3EE;--neutral-t80:#F8F9F6;--contrast:#141F06;--contrast-t30:#515A47;--contrast-t50:#7F8678;
--font-header:"Inter Tight",system-ui,sans-serif;--font-title:"Inter",system-ui,sans-serif;--font-para:"Open Sans",system-ui,sans-serif}
*{box-sizing:border-box}
body{margin:0;background:var(--neutral-t80);color:var(--contrast);font:400 16px/1.6 var(--font-para)}
header{background:var(--contrast);color:#fff;padding:40px 24px}
.wrap{max-width:960px;margin:0 auto;padding:0 24px}
header .wrap{padding:0}
header .mark{font:700 14px var(--font-title);letter-spacing:.14em;text-transform:uppercase;color:var(--primary)}
h1{font:700 clamp(28px,5vw,44px)/1.1 var(--font-header);margin:6px 0 4px}
header p{margin:0;color:var(--neutral)}
h2{font:700 26px/1.2 var(--font-header);margin:0 0 12px}
main{padding:32px 0 56px}
.card{background:#fff;border:1px solid var(--neutral);border-radius:16px;padding:28px;margin:0 0 24px}
.lead{font-size:19px;line-height:1.5;margin:0 0 12px}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:16px 0 4px}
.fact{background:var(--neutral-t80);border-radius:12px;padding:12px 14px}
.fact b{display:block;font:700 24px var(--font-header)}
.fact span{font-size:13px;color:var(--contrast-t30)}
.flag{border-left:4px solid #FE80DA;background:var(--accent-t60);color:var(--accent-s50);border-radius:0 12px 12px 0;padding:10px 14px;margin:8px 0}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:14px}
th{font:600 12px var(--font-title);text-align:left;color:var(--contrast-t30);padding:8px 10px;border-bottom:2px solid var(--neutral)}
td{padding:8px 10px;border-bottom:1px solid var(--neutral-t60);vertical-align:top}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td.new{background:#E8FFD1}
.muted{color:var(--contrast-t50);font-size:13px}
ol,ul{padding-left:22px;margin:6px 0}
li{margin:4px 0}
a{color:var(--primary-s40);overflow-wrap:anywhere}
code{background:var(--neutral-t60);padding:1px 5px;border-radius:4px;font-size:13px}
footer{color:var(--contrast-t50);font-size:13px;padding:0 0 40px}
@media print{body{background:#fff}.card{break-inside:avoid-page;border-color:#ccc}}
"""


def esc(x) -> str:
    return html.escape("" if x is None else str(x))


def num(x) -> str:
    if x is None or x == "":
        return "n/a"
    x = float(x)
    return f"{int(x):,}" if x.is_integer() else f"{x:,.1f}"


def _guide(code: str) -> str:
    key = GUIDE_FOR.get(code, "")
    if not key:
        return ""
    text, link = FIX_GUIDE[key]
    return esc(text) + (f' <a href="{esc(link)}">Wix help</a>' if link else "")


def _page(title: str, subtitle: str, body: str) -> str:
    fonts = ("https://fonts.googleapis.com/css2?family=Inter+Tight:wght@700&family=Inter:wght@600"
             "&family=Open+Sans:wght@400;600&display=swap")
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title>'
            f'<link rel="stylesheet" href="{fonts}"><style>{CSS}</style></head><body>'
            f'<header><div class="wrap"><div class="mark">Wix Site Doctor</div><h1>{esc(title)}</h1>'
            f'<p>{esc(subtitle)}</p></div></header><main><div class="wrap">{body}</div></main>'
            f'<footer><div class="wrap">Made with Wix Site Doctor. Every number comes from the pages that were read; '
            f'the writing is drafted by Claude and checked against them.</div></footer></body></html>')


def render_report(audit: dict, summary: dict, fixes: dict | None, out_dir: Path) -> Path:
    t = audit["totals"]
    site = audit["site"]
    body = [f'<section class="card"><p class="lead"><b>{esc(summary.get("headline"))}</b></p>'
            + "".join(f"<p>{esc(p)}</p>" for p in summary.get("summary", []))
            + '<div class="facts">'
            f'<div class="fact"><b>{num(t["pages_checked"])}</b><span>Pages checked</span></div>'
            f'<div class="fact"><b>{num(t["pages_with_issues"])}</b><span>Pages with something to fix</span></div>'
            f'<div class="fact"><b>{num(t["images_alt_file_name"])}</b><span>Images whose alt text is a file name</span></div>'
            f'<div class="fact"><b>{num(len(audit["site_issues"]))}</b><span>Site-wide issues</span></div></div></section>']
    if audit["site_issues"]:
        body.append('<section class="card"><h2>Site-wide</h2>' + "".join(
            f'<div class="flag"><b>{esc(s["text"])}.</b><br><span class="muted">{_guide(s["code"])}</span></div>'
            for s in audit["site_issues"]) + "</section>")
    counts = t["issue_counts"]
    if counts:
        rows = "".join(f'<tr><td>{esc(ISSUE_TEXT[c])}</td><td class="n">{n}</td><td class="muted">{_guide(c)}</td></tr>'
                       for c, n in counts.items())
        body.append('<section class="card"><h2>What we found, and where to fix it in Wix</h2><div class="scroll"><table>'
                    f'<tr><th>Issue</th><th class="n">Pages</th><th>Where to fix it</th></tr>{rows}</table></div></section>')
    pages = {p["url"]: p for p in audit["pages"]}
    top = [pages[u] for u in audit["rewrite_queue"][:15]]
    if top:
        rows = "".join(f'<tr><td><a href="{esc(p["url"])}">{esc(p["path"])}</a><br><span class="muted">{esc(p["title"])}</span></td>'
                       f'<td>{"<br>".join(esc(x) for x in p["issue_text"])}</td></tr>' for p in top)
        body.append('<section class="card"><h2>Pages to fix first</h2><div class="scroll"><table>'
                    f'<tr><th>Page</th><th>Issues</th></tr>{rows}</table></div></section>')
    if fixes and fixes.get("pages"):
        rows = "".join(
            f'<tr><td>{esc(pages.get(f["url"], {}).get("path", f["url"]))}</td>'
            f'<td>{esc(pages.get(f["url"], {}).get("title", ""))}</td><td class="new">{esc(f.get("new_title") or "(keep)")}</td>'
            f'<td class="new">{esc(f.get("new_description") or "(keep)")}</td><td>{esc(f.get("reason"))}</td></tr>'
            for f in fixes["pages"])
        body.append('<section class="card"><h2>Proposed titles and descriptions</h2><div class="scroll"><table>'
                    '<tr><th>Page</th><th>Current title</th><th>New title</th><th>New description</th><th>Why</th></tr>'
                    f'{rows}</table></div><p class="muted">The full list, with a column for sign-off, is in wix_fixes.xlsx.</p></section>')
    if summary.get("next_steps"):
        body.append('<section class="card"><h2>Next steps</h2><ol>'
                    + "".join(f"<li>{esc(s)}</li>" for s in summary["next_steps"]) + "</ol></section>")
    notes = list(audit.get("notes", []))
    secs = ", ".join(f"{k} ({v})" for k, v in audit["sections"].items())
    if secs:
        notes.insert(0, f"sitemap sections read: {secs}")
    body.append('<section class="card"><h2>About this check</h2><ul>' + "".join(f"<li>{esc(n)}</li>" for n in notes)
                + '</ul><p class="muted">Length limits follow Wix\'s own guidance: titles under '
                f'{audit["thresholds"]["title_max_chars"]} characters, descriptions '
                f'{audit["thresholds"]["description_min_chars"]} to {audit["thresholds"]["description_max_chars"]}. '
                "Only public pages were read; nothing on the site was changed.</p></section>")
    name = summary.get("client") or site["site_name"] or site["origin"]
    path = out_dir / "wix_audit.html"
    path.write_text(_page(summary.get("title") or "Wix site check", f"{name} · {site['origin']}", "".join(body)),
                    encoding="utf-8")
    return path


TITLE_COLS = ["Priority", "Page", "Type", "Current title", "Chars", "New title", "Chars", "Current description",
              "Chars", "New description", "Chars", "What was wrong", "Why this change", "Where to paste it",
              "Approved? (yes / no / edit)", "Reviewer notes"]
ALT_COLS = ["Page", "Image file", "Image link", "Current alt text", "New alt text", "Written from",
            "Where to paste it", "Approved? (yes / no / edit)", "Reviewer notes"]


def render_fixes(audit: dict, fixes: dict, out_dir: Path) -> list[Path]:
    pages = {norm_url(p["url"]): p for p in audit["pages"]}
    order = {norm_url(u): i for i, u in enumerate(audit["rewrite_queue"])}
    items = sorted(fixes.get("pages", []), key=lambda f: order.get(norm_url(f["url"]), len(order)))
    where_title = FIX_GUIDE["title"][0]
    trows = []
    for i, f in enumerate(items, 1):
        p = pages[norm_url(f["url"])]
        nt, nd = str(f.get("new_title", "")).strip(), str(f.get("new_description", "")).strip()
        trows.append([i, p["path"], p["section"], p["title"], p["title_chars"], nt or "(keep current)",
                      len(nt) if nt else "", p["description"], p["description_chars"], nd or "(keep current)",
                      len(nd) if nd else "", "; ".join(x for x, c in zip(p["issue_text"], p["issues"])
                                                       if c.startswith(("title", "description", "home"))),
                      f.get("reason", ""), where_title, "", ""])
    arows = []
    shared = {i["image"]: i for i in audit.get("shared_images", [])}
    for a in fixes.get("alt_text", []):
        p = pages[norm_url(a["url"])]
        img = next((i for i in p["image_fixes"] if i["image"] == a["image"]), None) or shared[a["image"]]
        where = p["path"] if a["image"] not in shared else f"Header or footer (on {img['pages']} pages)"
        arows.append([where, img["file"], img.get("src", ""), img["alt"], "(decorative: leave empty)"
                      if a.get("decorative") and not a.get("new_alt") else a.get("new_alt", ""),
                      a.get("basis", ""), FIX_GUIDE["alt"][0], "", ""])
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, cols, rows in [("wix_fixes_titles.csv", TITLE_COLS, trows), ("wix_fixes_alt_text.csv", ALT_COLS, arows)]:
        if rows:
            path = out_dir / name
            with path.open("w", newline="", encoding="utf-8-sig") as fh:
                w = csv.writer(fh)
                w.writerow(cols)
                w.writerows(rows)
            written.append(path)
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        return written
    wb = Workbook()
    wb.remove(wb.active)
    new_fill, ok_fill = PatternFill("solid", fgColor="E8FFD1"), PatternFill("solid", fgColor="FFE8F7")
    for title, cols, rows, widths, green, pink in [
            ("Titles and descriptions", TITLE_COLS, trows, [8, 30, 12, 40, 7, 40, 7, 46, 7, 46, 7, 34, 40, 40, 20, 26], (5, 9), 14),
            ("Alt text", ALT_COLS, arows, [28, 30, 40, 28, 44, 16, 50, 20, 26], (4,), 7)]:
        if not rows:
            continue
        ws = wb.create_sheet(title)
        ws.append(cols)
        for r in rows:
            ws.append(r)
        for i, wdt in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = wdt
            c = ws.cell(row=1, column=i)
            c.font = Font(bold=True, color="C1FF72")
            c.fill = PatternFill("solid", fgColor="141F06")
            c.alignment = Alignment(wrap_text=True, vertical="center")
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top")
            for g in green:
                row[g].fill = new_fill
            row[pink].fill = ok_fill
        ws.freeze_panes = "C2"
    info = wb.create_sheet("Read me")
    T = audit["thresholds"]
    for line in ["How to use this sheet",
                 "Green columns are the proposed changes. Pink is for your decision: yes, no or edit.",
                 f"Titles are kept under {T['title_max_chars']} characters and descriptions between "
                 f"{T['description_min_chars']} and {T['description_max_chars']}, following Wix's own guidance.",
                 "The 'Where to paste it' column says where each change goes in Wix. Wix renames menus from time to "
                 "time; if a step doesn't match, search the Wix Help Center for the setting's name.",
                 "Publish the site after making the changes so they go live.", "", "About the data"] + audit.get("notes", []):
        info.append([line])
    info.column_dimensions["A"].width = 120
    info["A1"].font = Font(bold=True, size=14)
    path = out_dir / "wix_fixes.xlsx"
    wb.save(path)
    written.append(path)
    return written


def render_redirects(redirects: list[dict], unresolved: list[dict], out_dir: Path, per_file: int = 500) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("redirects*.csv"):
        old.unlink()
    written = []
    chunks = [redirects[i:i + per_file] for i in range(0, len(redirects), per_file)] or [[]]
    for n, chunk in enumerate(chunks, 1):
        name = "redirects.csv" if len(chunks) == 1 else f"redirects-{n:02d}.csv"
        path = out_dir / name
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["Old URL", "New URL"])
            w.writerows([[r["old"], r["new"]] for r in chunk])
        written.append(path)
    path = out_dir / "redirects_review.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["Old URL", "Impressions", "Status", "Suggested new URL", "Other candidates", "Your decision"])
        for r in unresolved:
            w.writerow([r["old_url"], "" if r["impressions"] is None else r["impressions"],
                        "suggested, not approved" if r["match"] == "suggested" else "no match",
                        r["new_path"], " ".join(r["candidates"]), ""])
        for r in redirects:
            w.writerow([r["old"], "", f"in redirect file ({r.get('how') or 'set'})", r["new"], "", ""])
    written.append(path)
    return written
