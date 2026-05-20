"""
Radio Polar — radiopolar.com
robots.txt: general crawling allowed, Crawl-delay: 1.

Method: sitemap index (/sitemap/news/sitemap.xml) → 100 sub-sitemaps ×
100 URLs = ~10,000 articles. Each article fetched via the Next.js data API:
  /_next/data/{buildId}/{slug}.json → route.post (title, date, body)

BuildId is read from the homepage __NEXT_DATA__ block and refreshed
automatically if a request returns 404 (happens after site redeployment).

Limitation: sitemap covers approximately the last 12 months only.
There is no server-accessible way to enumerate older articles — the JS
listing page requires a headless browser to paginate, and the CMS API
returns 401 for the public app token.
"""
import re
import json
import logging
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from .base import BaseScraper

logger = logging.getLogger(__name__)

SITEMAP_INDEX = "https://www.radiopolar.com/sitemap/news/sitemap.xml"
BASE          = "https://www.radiopolar.com"
SM_NS         = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


class RadioPolarScraper(BaseScraper):
    name      = "Radio Polar"
    base_url  = BASE
    min_delay = 1.0

    def _get_build_id(self):
        r = self.get(BASE + "/", delay=0.5)
        if not r:
            return None
        m = re.search(r'"buildId":"([^"]+)"', r.text)
        return m.group(1) if m else None

    def _iter_sitemap_slugs(self, date_from, date_to):
        """
        Yield (slug, url) from all news sub-sitemaps.
        Sitemaps have no date field, so all slugs are yielded and date
        filtering happens after fetching the article data.
        """
        r = self.get(SITEMAP_INDEX, delay=1.0)
        if not r:
            return
        try:
            root = ET.fromstring(r.content)
        except ET.ParseError:
            logger.warning("Could not parse Radio Polar sitemap index")
            return

        sub_urls = [
            el.findtext("sm:loc", "", SM_NS)
            for el in root.findall("sm:sitemap", SM_NS)
        ]
        yield from self._iter_sub_sitemap_slugs(sub_urls)

    def _iter_sub_sitemap_slugs(self, sub_urls):
        for sub_url in sub_urls:
            r = self.get(sub_url, delay=1.0)
            if not r:
                continue
            try:
                root = ET.fromstring(r.content)
            except ET.ParseError:
                continue
            for url_el in (root.findall("sm:url", SM_NS) or root.findall("url")):
                loc = url_el.findtext("sm:loc", "", SM_NS) or url_el.findtext("loc", "")
                if not loc:
                    continue
                slug = loc.rstrip("/").split("/")[-1]
                if slug and "-" in slug and len(slug) > 10:
                    yield slug, loc

    def _fetch_article(self, slug, url, build_id):
        data_url = f"{BASE}/_next/data/{build_id}/{slug}.json"
        r = self.get(data_url, delay=self.min_delay)
        if not r:
            return None, False

        if r.status_code == 404:
            return None, True   # signal stale buildId

        try:
            post = (r.json()
                    .get("pageProps", {})
                    .get("data", {})
                    .get("route", {})
                    .get("post", {}))
        except Exception:
            return None, False

        if not post.get("title"):
            return None, False

        body_html = post.get("description", "")
        soup = BeautifulSoup(body_html, "lxml")
        body_text = re.sub(r"\s+", " ", soup.get_text(separator=" ")).strip()

        tags = [t.get("name", "") for t in post.get("tags", [])]
        section = ", ".join(t for t in tags if t)[:120]

        return {
            "source":    "Radio Polar",
            "date":      (post.get("datePublished") or "")[:10],
            "title":     post.get("title", ""),
            "url":       url,
            "body_text": body_text,
            "section":   section,
        }, False

    def run(self, query="", date_from="", date_to="", delay=1.5):
        actual_delay = max(delay, self.min_delay)

        yield {"type": "log", "level": "info", "msg": "Fetching buildId from homepage…"}
        build_id = self._get_build_id()
        if not build_id:
            yield {"type": "log", "level": "error", "msg": "Could not get Next.js buildId"}
            return
        yield {"type": "log", "level": "info", "msg": f"BuildId: {build_id}"}

        query_lower = query.lower().strip()
        total = 0

        for slug, url in self._iter_sitemap_slugs(date_from, date_to):
            article, stale = self._fetch_article(slug, url, build_id)

            if stale:
                yield {"type": "log", "level": "warn",
                       "msg": "BuildId stale — refreshing…"}
                build_id = self._get_build_id()
                if not build_id:
                    yield {"type": "log", "level": "error",
                           "msg": "Could not refresh buildId, stopping"}
                    break
                article, _ = self._fetch_article(slug, url, build_id)

            if not article:
                yield {"type": "fail", "url": url}
                continue

            art_date = article.get("date", "")
            if not self.in_date_range(art_date, date_from, date_to):
                continue

            if query_lower:
                haystack = f"{article.get('title','')} {article.get('body_text','')}".lower()
                if query_lower not in haystack:
                    continue

            yield {"type": "article", "data": article}
            total += 1

        yield {"type": "log", "level": "info",
               "msg": f"Done — {total} articles collected"}
