"""Run with `python -m unittest discover tests`. Uses only the local sample site: no network."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "wix-site-doctor" / "scripts"
SAMPLE = ROOT / "sample-data" / "willow-and-fern"
EXAMPLE = ROOT / "examples" / "willow-and-fern"
SITE = "https://www.willowandfern.example"
sys.path.insert(0, str(SCRIPTS))

from doctor_core import audit, check, migrate, page, render  # noqa: E402
from doctor_core.fetch import Source, parse_sitemap, section_name  # noqa: E402


def run_audit():
    notes: list[str] = []
    src = Source(str(SAMPLE / "new-wix-site"))
    pages, sections = audit.crawl(src, 150, notes)
    return audit.build(pages, sections, SITE, {}, notes, 150)


class Parsing(unittest.TestCase):
    def test_page_facts(self):
        info = page.parse((SAMPLE / "new-wix-site" / "about-3.html").read_text())
        self.assertEqual(info["title"], "About | Willow & Fern")
        self.assertEqual(info["description"], "About us.")
        self.assertTrue(info["is_wix"])
        self.assertIn(page.WIX_DEFAULT_FAVICON, info["favicon"])
        self.assertEqual(info["h1"], ["Our story"])

    def test_images_deduplicated_by_media_id(self):
        html = ('<img src="https://static.wixstatic.com/media/ab_12~mv2.jpg/v1/fill/w_100/a.jpg" alt="a.jpg">'
                '<img src="https://static.wixstatic.com/media/ab_12~mv2.jpg/v1/fill/w_900/a.jpg" alt="a.jpg">')
        self.assertEqual(len(page.parse(html)["images"]), 1)

    def test_sitemap_parsing(self):
        kind, items = parse_sitemap((SAMPLE / "new-wix-site" / "sitemap.xml").read_text())
        self.assertEqual(kind, "index")
        self.assertEqual(len(items), 2)
        self.assertEqual(section_name("https://x.com/dynamic-team_p_c7cc964c_0_5000-sitemap.xml"), "dynamic: team")
        self.assertEqual(parse_sitemap("<html>Connect your domain</html>")[0], "invalid")

    def test_file_name_alt(self):
        for alt, f in [("IMG_4821.JPG", "IMG_4821.JPG"), ("Untitled_Artwork 10.jpg", "x.jpg"), ("bg", "bg.jpg"),
                       ("Screenshot 2026-03-02 at 10.14.22.png", "s.png"), ("DSC_0042", "d.jpg")]:
            self.assertTrue(audit.alt_looks_like_file_name(alt, f), alt)
        for alt in ["Bridal bouquet of white peonies", "Sara and Tom arranging peonies"]:
            self.assertFalse(audit.alt_looks_like_file_name(alt, "x.jpg"), alt)

    def test_slug_issues(self):
        self.assertEqual(audit.slug_issue("/about-5"), "url_auto_numbered")
        self.assertEqual(audit.slug_issue("/copy-of-anz-media"), "url_copy_of")
        self.assertEqual(audit.slug_issue("/blank-1"), "url_blank")
        self.assertIsNone(audit.slug_issue("/wedding-flowers"))
        self.assertIsNone(audit.slug_issue("/2024-trailblazer"))


class Auditing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = run_audit()
        cls.pages = {p["path"]: p for p in cls.a["pages"]}

    def test_reads_whole_sample(self):
        self.assertEqual(self.a["sections"], {"blog-posts": 2, "pages": 8})
        self.assertEqual(self.a["totals"]["pages_loaded"], 10)
        self.assertEqual(self.a["site"]["site_name"], "Willow & Fern")

    def test_planted_issues_found(self):
        p = self.pages
        self.assertIn("home_title_default", p["/"]["issues"])
        self.assertIn("title_looks_default", p["/about-3"]["issues"])
        self.assertNotIn("title_too_short", p["/about-3"]["issues"])  # default title is not double-counted
        self.assertIn("title_looks_default", p["/copy-of-weddings"]["issues"])
        self.assertIn("url_copy_of", p["/copy-of-weddings"]["issues"])
        self.assertIn("noindex_in_sitemap", p["/blank-1"]["issues"])
        self.assertIn("canonical_elsewhere", p["/shop-1"]["issues"])
        self.assertIn("description_duplicate", p["/workshops"]["issues"])
        self.assertIn("h1_multiple", p["/workshops"]["issues"])
        self.assertIn("title_too_long", p["/post/spring-wedding-flowers-guide"]["issues"])
        self.assertNotIn("title_looks_default", p["/post/how-to-make-cut-flowers-last-longer"]["issues"])
        self.assertEqual(p["/contact"]["issues"], ["social_image_missing"])

    def test_site_wide(self):
        codes = {s["code"] for s in self.a["site_issues"]}
        self.assertEqual(codes, {"default_favicon", "shared_alt_is_file_name"})
        self.assertEqual([i["file"] for i in self.a["shared_images"]], ["Willow-Logo-Final.png"])
        self.assertFalse(any(f["file"] == "Willow-Logo-Final.png" for pg in self.a["pages"] for f in pg["image_fixes"]))

    def test_unconnected_domain(self):
        bad = page.parse("<html><head><title>ConnectYourDomain Error | Wix.com</title></head></html>")
        bad.update(url=SITE, section="pages", status=200, error="", final_url=SITE)
        result = audit.build([bad], {}, SITE)
        self.assertIn("domain_not_connected", {s["code"] for s in result["site_issues"]})
        self.assertIn("page_error", result["pages"][0]["issues"])

    def test_impressions_order(self):
        notes: list[str] = []
        pages, sections = audit.crawl(Source(str(SAMPLE / "new-wix-site")), 150, notes)
        imps = {audit.norm_url(SITE + "/weddings"): 9999.0}
        result = audit.build(pages, sections, SITE, imps, notes)
        self.assertEqual(result["rewrite_queue"][0], SITE + "/weddings")


class Fixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = json.loads((EXAMPLE / "audit.json").read_text())
        cls.fixes = json.loads((EXAMPLE / "fixes.json").read_text())

    def test_example_passes(self):
        errors, _ = check.check_fixes(self.a, self.fixes)
        self.assertEqual(errors, [])

    def test_blocks_bad_work(self):
        f = copy.deepcopy(self.fixes)
        f["pages"][0]["new_title"] = "x" * 61
        f["pages"][1]["new_title"] = "Visit or Call Our Bath Flower Studio | Willow & Fern"  # taken by /contact
        f["pages"][2]["new_description"] = "Too short."
        f["alt_text"][1]["new_alt"] = "IMG_4821.JPG"
        del f["alt_text"][2]["basis"]
        f["pages"].append({"url": SITE + "/nope", "new_title": "x", "reason": "r"})
        errors, _ = check.check_fixes(self.a, f)
        text = " ".join(errors)
        for needle in ["limit is 60", "already used", "at least 50", "still looks like a file name",
                       "set basis", "not a page that loaded"]:
            self.assertIn(needle, text)

    def test_summary_numbers_must_trace(self):
        s = json.loads((EXAMPLE / "summary.json").read_text())
        self.assertEqual(check.check_summary(self.a, s, self.fixes)[0], [])
        s["headline"] = "37 pages have problems."
        self.assertTrue(check.check_summary(self.a, s, self.fixes)[0])


class Redirects(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        notes: list[str] = []
        old = migrate.read_old_urls([str(SAMPLE / "old-wordpress-sitemap.xml")], notes)
        new = [{"url": SITE + ("" if p == "/" else p), "title": ""} for p in
               ["/", "/about-3", "/weddings", "/copy-of-weddings", "/workshops", "/contact", "/blank-1", "/shop-1",
                "/post/how-to-make-cut-flowers-last-longer", "/post/spring-wedding-flowers-guide"]]
        cls.plan = migrate.plan(old, new)
        cls.rows = {r["path"]: r for r in cls.plan["rows"]}

    def test_matching(self):
        r = self.rows
        self.assertEqual(r["/workshops"]["match"], "same_path")
        self.assertEqual(r["/2024/03/how-to-make-cut-flowers-last-longer"]["match"], "same_slug")
        self.assertEqual(r["/shop"]["match"], "suggested")
        self.assertEqual(r["/shop"]["new_path"], "/shop-1")
        self.assertEqual(r["/gallery"]["match"], "none")
        self.assertEqual({s["path"] for s in self.plan["skipped"]},
                         {"/tag/peonies", "/wp-content/uploads/2024/03/peonies.jpg"})

    def test_only_certain_matches_are_automatic(self):
        redirects, unresolved, errors, _ = check.resolve_redirects(self.plan, None)
        self.assertEqual(errors, [])
        self.assertEqual(len(redirects), 2)
        self.assertEqual({u["path"] for u in unresolved}, {"/about-us", "/wedding-flowers", "/shop",
                                                           "/flower-subscriptions", "/gallery"})

    def test_blocks_bad_targets(self):
        d = {"set": [{"old": "/gallery", "new": "/not-a-page", "reason": "r"},
                     {"old": "/flower-subscriptions", "new": "/post/spring-wedding-flowers-guide?lang=fr", "reason": "r"}],
             "approve_suggested": ["/workshops"]}
        _, _, errors, _ = check.resolve_redirects(self.plan, d)
        text = " ".join(errors)
        self.assertIn("not a page on the new site", text)
        self.assertIn("?lang=", text)
        self.assertIn("only applies to suggested", text)

    def test_files_split_at_500(self):
        many = [{"old": f"/old-{i}", "new": "/contact"} for i in range(1201)]
        with tempfile.TemporaryDirectory() as d:
            paths = render.render_redirects(many, [], Path(d))
            names = sorted(p.name for p in paths)
            self.assertEqual(names, ["redirects-01.csv", "redirects-02.csv", "redirects-03.csv", "redirects_review.csv"])
            lines = (Path(d) / "redirects-01.csv").read_text().splitlines()
            self.assertEqual(lines[0], "Old URL,New URL")
            self.assertEqual(len(lines), 501)


class CommandLine(unittest.TestCase):
    def test_end_to_end(self):
        cli = str(SCRIPTS / "wixdoctor.py")
        with tempfile.TemporaryDirectory() as d:
            run = lambda *a: subprocess.run([sys.executable, cli, *a], capture_output=True, text=True)  # noqa: E731
            self.assertEqual(run("audit", str(SAMPLE / "new-wix-site"), "--out", d).returncode, 0)
            for name in ["fixes.json", "summary.json", "redirect_decisions.json"]:
                (Path(d) / name).write_text((EXAMPLE / name).read_text())
            r = run("render", "--out", d)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertTrue((Path(d) / "wix_audit.html").exists())
            self.assertEqual(run("migrate", "--old", str(SAMPLE / "old-wordpress-sitemap.xml"), "--new",
                                 str(SAMPLE / "new-wix-site"), "--out", d).returncode, 0)
            r = run("render-redirects", "--out", d)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertIn("6 redirect(s)", r.stdout)


if __name__ == "__main__":
    unittest.main()
