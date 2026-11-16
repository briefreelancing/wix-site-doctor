<img src="assets/wix-site-doctor-logo.png" alt="Wix Site Doctor logo" width="120">

# Wix Site Doctor

**A Claude skill that audits a Wix website for the SEO problems Wix leaves behind, and turns them into
fixes a site owner can paste in.**

Point it at a Wix site and get back:

- **A client-ready report** (`wix_audit.html`): what is wrong, which pages to fix first, and where
  each fix lives in Wix.
- **A fix sheet** (`wix_fixes.xlsx`): new titles, descriptions and alt text, old next to new, with
  where to paste each one and a column for sign-off.
- **Redirect files** (`redirects.csv`), for a site moving to Wix: ready to import into Wix's URL
  Redirect Manager.

It only reads public pages, one at a time with a pause between requests, and respects robots.txt.
It never logs in and never changes the site.

Not affiliated with or endorsed by Wix.com. "Wix" is a trademark of Wix.com Ltd.

## What it checks

| Check | Why it matters on Wix |
|---|---|
| Default titles | Wix titles every page "Page name \| Site name" (the home page: just the site name) until someone changes it |
| Missing descriptions | Wix leaves meta descriptions blank by default |
| Alt text that is a file name | Wix fills alt text with the uploaded file name, like `IMG_4821.JPG` or `Untitled_Artwork 10.jpg` |
| Leftover page URLs | `/about-5`, `/copy-of-services`, `/blank-1` from duplicated or renamed pages |
| Social share image | None by default unless set for the whole site |
| Default favicon | Wix's own icon until a custom one is uploaded (needs a Premium plan and domain) |
| Indexing mistakes | Pages in the sitemap that say noindex, canonicals pointing elsewhere, redirects |
| Unconnected domain | Wix's "Connect Your Domain" error page served instead of the site |
| Headings | No H1, or several |

Header and footer images that appear on most pages are reported once, as site-wide.

## How it works

```
site URL ─► sitemap index ─► pages-, blog-posts-, store-…-sitemap.xml ─► each page's HTML
                                                                          │
               audit.json (every check, counts, fix order) ◄──────────────┘
                     │
   Claude writes fixes.json + summary.json ─► gatekeeper ─► wix_audit.html, wix_fixes.xlsx

old sitemap / crawl / Search Console ─► match to new Wix pages ─► redirect_plan.json
   Claude + user decide unmatched ones ─► gatekeeper ─► redirects.csv (500 per file)
```

The rule from Readout and Vinci applies: **scripts calculate, Claude writes.** The gatekeeper
refuses to render when:

- a title is 60 characters or more, or a description is outside 50 to 160 (Wix's own guidance)
- two pages would share a title or description
- new alt text still looks like a file name, or has no stated basis (seen, owner description, file name)
- the summary quotes a number that isn't in the audit
- a redirect points to a page that doesn't exist, to itself, into a chain, or uses `?lang=`
- the home page would be redirected

Only redirects whose page name matches exactly go in automatically. Close matches need a yes.

## Run it

```bash
python skills/wix-site-doctor/scripts/wixdoctor.py audit https://www.example.com --out out
python skills/wix-site-doctor/scripts/wixdoctor.py migrate --old old-sitemap.xml --new https://www.example.com --out out
```

Python 3.9+, standard library only. `openpyxl` adds the Excel sheet.

## Try it with the sample data

`sample-data/willow-and-fern/` holds a fictional Wix florist site saved as local files, with
problems planted, plus its old WordPress sitemap and a Search Console export. The finished
outputs are in `examples/willow-and-fern/`.

```bash
python tools/make_sample_data.py
python skills/wix-site-doctor/scripts/wixdoctor.py audit sample-data/willow-and-fern/new-wix-site --out out \
  --gsc sample-data/willow-and-fern/gsc_pages.csv
```

## Tested on

The sample site, plus read-only runs on six live Wix sites (bakeries, a shop, a design portfolio,
a nonprofit with a blog and dynamic pages, and one with an unconnected domain). Wix's redirect
format, default SEO settings and fix locations come from the Wix Help Center (November 2026).

## Package

```bash
python -m unittest discover tests
python tools/package_skill.py
```

writes `dist/wix-site-doctor.zip`, with one folder and `SKILL.md` at its root.

Built by Brie and Claude.
