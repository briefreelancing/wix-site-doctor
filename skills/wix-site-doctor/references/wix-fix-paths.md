# Where each fix goes in Wix

Taken from the Wix Help Center (checked November 2026). Wix renames menus from time to time; if a
step doesn't match what the user sees, search the Help Center for the setting's name.

## Page title and meta description
Editor: **Pages & Menu**, the page's **More Actions** icon, **Settings**, then the SEO tab.
Blog posts and store products have their own SEO settings.
Wix's guidance: titles under 60 characters, descriptions 50 to 160, unique per page.
https://support.wix.com/en/article/adding-seo-title-tags-and-meta-descriptions-to-your-pages

Wix's defaults: the title is "Page name | Site name" (home page: the site name), the description
is blank, there is no social image unless one is set for the whole site.
https://support.wix.com/en/article/understanding-your-sites-default-seo-settings-6447365

## Image alt text
Single image: click it in the editor, **Settings**, then **What's in the image?**, and press Enter.
Pro Gallery: **Manage Media**, select the image, **Alt text**.
Alt text can't be added in bulk. Publish the site afterwards so it goes live.
https://support.wix.com/en/article/accessibility-preparing-your-images-and-galleries

## Page URL (slug)
Change it in the page's SEO settings. Wix creates a 301 redirect automatically for editor pages,
store products and categories, bookings services, events and online programs, but **not for blog
posts**: add those in the URL Redirect Manager.
https://support.wix.com/en/article/setting-up-a-301-redirect-for-a-page-on-your-site

## Favicon
Dashboard: **Settings**, **Website settings**, **Upload Image** under Favicon. Needs a Premium plan
and a connected domain. Size: a multiple of 48px square, or SVG.
https://support.wix.com/en/article/wix-editor-changing-your-favicon

## Importing redirects
Dashboard: **SEO & GEO**, scroll to **Tools and settings**, **URL Redirect Manager**,
**More Actions**, **Import redirects**, **Upload CSV File**, then **Import Redirects**.

- Two columns with a header row: old URL, then new URL. One redirect per row.
- Up to 500 redirects per file, 5,000 per site.
- Redirects only work on a connected custom domain, not a free wixsite.com address.
- A URL that already has a redirect is skipped unless the override toggle is switched on.
- If the import fails, download the CSV report: it lists the status of each row.
- Multilingual sites: choose the language first; redirects only work between pages in the same
  language, and the new URL can't contain `?lang=`.

https://support.wix.com/en/article/importing-or-exporting-url-redirects-with-a-csv-file
https://support.wix.com/en/article/setting-up-a-301-redirect-for-a-multilingual-site
