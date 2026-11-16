---
name: wix-site-doctor
description: Audit a Wix website for the SEO problems Wix leaves behind and turn them into fixes a site owner can paste in. Reads the site's public sitemap and pages (no Wix login) and flags default "Page name | Site name" titles, blank meta descriptions, alt text left as the uploaded file name, auto-numbered or "copy-of" page URLs, missing social images, the default Wix favicon, noindex or canonical mistakes and an unconnected domain. Writes a client-ready report and a fix sheet that says where each change goes in the Wix editor. For a site moving to Wix, matches the old site's URLs to the new pages and writes 301 redirect files ready to import into Wix's URL Redirect Manager. Use when someone asks to audit, check or fix SEO on a Wix site, prepare a Wix site for launch, or plan redirects for a migration to Wix.
---

# Wix Site Doctor

Checks a Wix site the way a careful SEO consultant would and hands back three things:

- **A client-ready report** (`wix_audit.html`): what is wrong, which pages to fix first, and where
  each fix lives in Wix.
- **A fix sheet** (`wix_fixes.xlsx`): new titles, descriptions and alt text, old next to new,
  with where to paste each one and a column for sign-off.
- **Redirect files** (`redirects.csv`), for a site moving to Wix: ready to import into Wix's URL
  Redirect Manager.

**Core rule: the scripts calculate, you write.** Reading pages, every check, counts and redirect
matching come from `wixdoctor.py`. You write the summary, the new titles, descriptions and alt
text, and decisions on unmatched redirects. The script refuses to render anything until your
writing agrees with the audit.

It only reads public pages, one at a time with a pause between requests, and respects
robots.txt. It never logs in and never changes the site.

## What the user provides

| Input | Needed for | Notes |
|---|---|---|
| The site address | Everything | For example `https://www.example.com`. A free `wixsite.com` address works too. |
| Search Console pages export | Optional: fix order | Orders pages by impressions instead of by issue count. |
| The old site's URLs | Migration only | The old `sitemap.xml` (file or live URL), a crawl export (Screaming Frog, Sitebulb), a Search Console pages export, or a `.txt` list. How to get them: `references/getting-old-urls.md`. |

## Workflow

1. **Ask** for the site address if you don't have it, and whether the site is moving from another
   platform. Don't ask anything else up front.
2. **Run the audit.** Python 3.9+; `openpyxl` only for the Excel sheet (install it if missing).

   ```bash
   python <this-skill-folder>/scripts/wixdoctor.py audit https://www.example.com --out wix_out \
     --client "Client name" [--gsc pages.csv] [--max-pages 150]
   ```

   Large sites: the first 150 URLs are checked (static pages first, then blog posts, then store
   pages). Say so, and offer `--max-pages` if they want more. At one request per second, 150 pages
   take about three minutes.
3. **Read `wix_out/audit.json`** and give the chat summary (format below). Then ask what they want:
   the client report, the fix sheet, redirects, or all of them.
4. **Fixes.** Write `wix_out/fixes.json` from `templates/fixes_template.json` (rules below), and
   `wix_out/summary.json` from `templates/summary_template.json`. Then:

   ```bash
   python <this-skill-folder>/scripts/wixdoctor.py render --out wix_out
   ```

   It prints errors and stops if anything fails the checks. Fix and rerun. A report needs only
   `summary.json`; the fix sheet appears when `fixes.json` exists.
5. **Redirects** (migration only):

   ```bash
   python <this-skill-folder>/scripts/wixdoctor.py migrate --old old-sitemap.xml --new https://www.example.com --out wix_out
   ```

   Read `wix_out/redirect_plan.json`. `same_slug` matches go in automatically. Show the user every
   `suggested` and `none` row, most impressions first, with your recommendation for each. Only after
   the user agrees, write `wix_out/redirect_decisions.json` from
   `templates/redirect_decisions_template.json`, then run
   `python <this-skill-folder>/scripts/wixdoctor.py render-redirects --out wix_out`.
6. **Send the files** and say in one line what each is for and who it goes to. For redirects, give
   the import steps from `references/wix-fix-paths.md`.

## Reading audit.json

| Key | Meaning |
|---|---|
| `site` | Site name, whether it identifies as Wix, languages |
| `sections` | URLs per sitemap section: `pages`, `blog-posts`, `store-products`, `dynamic: ...` |
| `totals` | Every count you may quote: pages checked, pages with issues, issue counts, images |
| `site_issues` | Site-wide problems: unconnected domain, free wixsite.com address, default favicon, no social image anywhere, header or footer images with file-name alt text |
| `rewrite_queue` | Page URLs in fix order: by impressions when Search Console data was given, otherwise home page first, then most serious issues |
| `pages[]` | Per page: `title`, `description`, `h1`, `issues`, `issue_text`, `image_fixes` (images on that page only) |
| `shared_images` | Images on most pages (header, footer); fix once, they update everywhere |
| `alt_queue` | Every image whose alt text is a file name, site-wide ones first |
| `thresholds` | The limits used: Wix's own guidance for titles (under 60) and descriptions (50 to 160); the rest are rules of thumb |
| `notes` | Data caveats. Mention the ones that affect the conclusions. |

## Writing fixes

- **Titles**: under 60 characters, unique across the site. Lead with what the page is about. Wix
  suggests "Keyword | Brand" or, for a local business, "Keyword | Location | Brand". Keep the site's
  usual ending (for example " | Acme Studio") if most titles have it.
- **Descriptions**: 50 to 160 characters, unique. Say what the visitor gets and why to click.
- **Describe only what the page shows.** You know each page from its URL, current title,
  description and H1. Don't invent prices, offers, awards, years in business or locations. If you
  can't tell what a page is for, say so in `reason` and keep the rewrite plain.
- **Alt text needs a basis.** You can't see an image from its file name. For each alt text set
  `basis` to `seen` (you viewed the image, for example the user uploaded it or you opened its
  link), `owner description` (the user told you), or `file name` (the name plainly says what it
  shows, like `chocolate-orange-cake.jpg`). Never write alt text for `Untitled_Artwork 10.jpg` or
  `IMG_2041.jpg` from the name alone: ask the user, or open the image link from `alt_queue` if you can
  view images. Mark purely decorative images with `"decorative": true` and no alt text.
- **Alt text style** (Wix's guidance): short, specific, different for each image on a page, no
  "image of" or "picture of".
- **reason**: one plain sentence for the reviewer: what was wrong and what the change does. Never
  promise a result ("will rank higher").

## Writing summary.json

- `headline`: one sentence with the main finding.
- `summary`: two or three short paragraphs. Every number must be in `audit.json` totals; the render
  refuses numbers it can't trace.
- `next_steps`: three to six steps, most important first, in plain words.
- Lead with site-wide problems that block everything else (unconnected domain, noindex).

## Redirect rules

- Only `same_slug` matches go in automatically. A `suggested` match needs the user's yes.
- A target must be a page on the new site, or a full external URL if the user says so.
- The home page is never redirected. Nothing redirects to itself or to a URL that is itself
  redirected.
- Wix takes up to 500 redirects per file and 5,000 per site; the script splits files at 500.
- Redirects only work on a connected custom domain, not a free wixsite.com address. Multilingual
  sites import redirects per language. Say this if it applies.

## Chat summary format

```
**What I read:** <pages checked> of <URLs in sitemap> pages (<sections>). <anything skipped and why>

**Site-wide:** <site_issues in one or two lines, or "nothing site-wide">

**Biggest problems:**
- <issue>: <pages> pages
- ... (3 to 5 lines, most serious first)

**Fix first:** <the first three pages in rewrite_queue, with their main issue>

<one line on caveats from notes>
Want the client report, the fix sheet, or both?
```

## Known limits

- Reads the HTML Wix serves to visitors. Things only visible in the editor (hidden pages, page
  names, mobile-only elements) are not checked.
- The default-title check matches Wix's "Page name | Site name" pattern with a short page name.
  A deliberate short title of that shape will be flagged too; say "looks like" in the report.
- The auto-numbered URL check flags URLs like `/about-5`. A URL like `/step-2` can be deliberate.
- Images shown on most pages are treated as header or footer images and reported once.
- Wix renames dashboard menus from time to time. The fix paths in `references/wix-fix-paths.md`
  come from the Wix Help Center; if a step doesn't match, search the Help Center for the setting.
- The checks confirm lengths, uniqueness, numbers and redirect targets. They cannot judge whether
  a title is persuasive. Read your work once before sending.
