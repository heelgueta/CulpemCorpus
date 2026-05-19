"""
Generic WordPress REST API scraper.
All WP-based sources inherit from WordPressScraper and set class-level constants.
"""
from html import unescape
import logging
from dateutil import parser as dateparser
from .base import BaseScraper

logger = logging.getLogger(__name__)

FIELDS = "id,date,title,link,content,categories"

# Browser-like UA for sites that block non-browser agents (e.g. itvpatagonia.com)
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class WordPressScraper(BaseScraper):
    """
    Scraper for any site with a public WordPress REST API at /wp-json/wp/v2/.

    Subclass and set:
        name      — display name
        base_url  — site root (no trailing slash)
        min_delay — respects robots.txt Crawl-delay
        use_browser_ua — set True if the site blocks non-browser User-Agents
    """
    name = "WordPress Site"
    base_url = ""
    min_delay = 1.0
    use_browser_ua = False

    def __init__(self):
        super().__init__()
        if self.use_browser_ua:
            self.session.headers["User-Agent"] = BROWSER_UA

    @property
    def _api(self):
        return f"{self.base_url}/wp-json/wp/v2"

    def _fetch_categories(self, delay):
        cats = {}
        page = 1
        while True:
            r = self.get(f"{self._api}/categories?per_page=100&page={page}", delay=0.3)
            if not r:
                break
            data = r.json()
            if not data:
                break
            for c in data:
                cats[c["id"]] = c["name"]
            if page >= int(r.headers.get("X-WP-TotalPages", 1)):
                break
            page += 1
        return cats

    def run(self, query="", date_from="", date_to="", delay=1.5):
        actual_delay = max(delay, self.min_delay)

        yield {"type": "log", "level": "info", "msg": "Fetching category index…"}
        categories = self._fetch_categories(actual_delay)

        params = {"per_page": 100, "_fields": FIELDS}
        if query:
            params["search"] = query
        if date_from:
            try:
                params["after"] = (
                    dateparser.parse(date_from).replace(hour=0, minute=0, second=0).isoformat()
                )
            except Exception:
                pass
        if date_to:
            try:
                params["before"] = (
                    dateparser.parse(date_to).replace(hour=23, minute=59, second=59).isoformat()
                )
            except Exception:
                pass

        page = 1
        total_pages = None

        while True:
            params["page"] = page
            r = self.get(f"{self._api}/posts", delay=actual_delay, params=params)

            if not r:
                yield {"type": "log", "level": "error", "msg": f"Failed on page {page}"}
                break

            if r.status_code == 400:
                yield {"type": "log", "level": "error", "msg": f"API error: {r.text[:200]}"}
                break

            if total_pages is None:
                total_pages = int(r.headers.get("X-WP-TotalPages", 1))
                total_posts = int(r.headers.get("X-WP-Total", 0))
                yield {
                    "type": "log", "level": "info",
                    "msg": f"{total_posts} posts across {total_pages} pages",
                }

            posts = r.json()
            if not posts:
                break

            for post in posts:
                cat_names = [categories.get(c, str(c)) for c in post.get("categories", [])]
                body_text = self.clean_html(post.get("content", {}).get("rendered", ""))
                title = unescape(post.get("title", {}).get("rendered", ""))

                yield {
                    "type": "article",
                    "data": {
                        "source": self.name,
                        "date": post.get("date", "")[:10],
                        "title": title,
                        "url": post.get("link", ""),
                        "body_text": body_text,
                        "section": ", ".join(cat_names),
                    },
                }

            if page >= total_pages:
                break
            page += 1
