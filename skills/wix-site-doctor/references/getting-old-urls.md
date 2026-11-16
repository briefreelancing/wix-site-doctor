# Getting the old site's URLs

Any one of these works; several can be given together and are merged.

- **The old sitemap** (best, if the old site is still live): give its address, for example
  `https://old-site.com/sitemap.xml` or `https://old-site.com/sitemap_index.xml`. WordPress, Squarespace
  and Shopify all publish one. If the old site is already gone, a saved copy of the file works.
- **A crawl export**: Screaming Frog (Internal tab, filter HTML, Export) or Sitebulb (URL Explorer,
  Internal HTML, Export). Pages that returned 3xx, 4xx or 5xx are left out.
- **A Search Console pages export**: Performance, Pages tab, Export. This adds impressions, so the
  pages that matter most are reviewed first. It also catches old URLs Google still shows that the
  sitemap forgot.
- **A plain list**: a `.txt` file with one URL per line.

Images, scripts, feeds, tag, author and pagination URLs are skipped automatically; the plan lists
them under `skipped`.

Do this **before** the old site is switched off: once the domain points at Wix, the old sitemap is gone.
