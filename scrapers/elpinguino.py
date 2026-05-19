"""
El Pingüino — elpinguino.com

Discovery: Internal JSON API GET /v2/home/search/{YYYY-MM-DD}
  → returns all articles for a date with title, excerpt, category, slug.
  One API call per day in the date range.

Full body: GET /noticia/{YYYY}/{MM}/{DD}/{slug}
  → single-article page with full text in .sit3-single-body (their CSS typo, not ours).
  One HTTP fetch per article.

Encoding: server claims UTF-8 but mis-sets headers; pass r.content to lxml and
  let it read the <meta charset> declaration.
"""
import re
import logging
from datetime import date, timedelta
from bs4 import BeautifulSoup
from .base import BaseScraper

logger = logging.getLogger(__name__)

DATE_API = "https://elpinguino.com/v2/home/search"
BASE = "https://www.elpinguino.com"


def iter_dates(date_from, date_to):
    try:
        d = date.fromisoformat(date_from)
        end = date.fromisoformat(date_to)
    except (ValueError, TypeError):
        return
    while d <= end:
        yield d.isoformat()
        d += timedelta(days=1)


class ElPinguinoScraper(BaseScraper):
    name = "El Pingüino"
    base_url = BASE
    min_delay = 1.0

    # ------------------------------------------------------------------ date API

    def _fetch_day(self, date_str, delay):
        r = self.get(f"{DATE_API}/{date_str}", delay=delay)
        if not r:
            return []
        try:
            data = r.json()
        except Exception:
            return []
        if data.get("info", {}).get("api_code") == 404:
            return []
        return data.get("result", [])

    # ------------------------------------------------------------------ article page

    def _fetch_body(self, url, delay):
        """Fetch the single-article page and return (body_text, title, date, section)."""
        r = self.get(url, delay=delay)
        if not r:
            return None

        # Pass raw bytes to lxml so it reads the <meta charset="UTF-8"> declaration
        soup = BeautifulSoup(r.content, "lxml")

        # Title
        title_el = soup.select_one(".site3-single h1")
        title = title_el.get_text(strip=True) if title_el else ""

        # Category
        cat_el = soup.select_one(".meta.cat")
        section = cat_el.get_text(strip=True) if cat_el else ""

        # Date — parse "18/05/2026 a las 08:09"
        date_str = ""
        for el in soup.select(".site3-meta-title .meta"):
            text = el.get_text(" ", strip=True)
            m = re.search(r"(\d{2})/(\d{2})/(\d{4})", text)
            if m:
                date_str = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
                break

        # Body — .sit3-single-body (their CSS typo, not ours)
        body_el = soup.select_one(".sit3-single-body")
        body_text = ""
        if body_el:
            for tag in body_el(["script", "style", "div"]):  # removes ad blocks
                tag.decompose()
            paragraphs = [p.get_text(strip=True) for p in body_el.find_all("p")
                          if p.get_text(strip=True)]
            body_text = " ".join(paragraphs)

        return title, date_str, section, body_text

    # ------------------------------------------------------------------ run

    def run(self, query="", date_from="", date_to="", delay=1.5):
        if not date_from or not date_to:
            yield {
                "type": "log", "level": "warn",
                "msg": "El Pingüino requires a date range — use From / To fields",
            }
            return

        query_lower = query.lower().strip()
        total_days = 0
        total_articles = 0

        for date_str in iter_dates(date_from, date_to):
            total_days += 1
            items = self._fetch_day(date_str, delay=delay)

            for item in items:
                api_title = item.get("post_title", "")
                api_excerpt = item.get("post_excerpt", "")

                # Apply query filter early on the cheap API data before fetching full page
                if query_lower:
                    if query_lower not in f"{api_title} {api_excerpt}".lower():
                        continue

                slug = item.get("post_slug", "")
                yyyy, mm, dd = date_str[:4], date_str[5:7], date_str[8:10]
                url = f"{BASE}/noticia/{yyyy}/{mm}/{dd}/{slug}"

                # Fetch full article page
                result = self._fetch_body(url, delay=delay)
                if result:
                    title, art_date, section, body_text = result
                else:
                    # Fall back to API data if page fetch fails
                    title, art_date, section, body_text = (
                        api_title,
                        date_str,
                        item.get("post_category", ""),
                        api_excerpt,
                    )

                # If body is empty (paywalled or failed), use excerpt as fallback
                if not body_text:
                    body_text = api_excerpt

                yield {
                    "type": "article",
                    "data": {
                        "source": "El Pingüino",
                        "date": art_date or date_str,
                        "title": title or api_title,
                        "url": url,
                        "body_text": body_text,
                        "section": section or item.get("post_category", ""),
                    },
                }
                total_articles += 1

            if total_days % 10 == 0:
                yield {
                    "type": "log", "level": "info",
                    "msg": f"  Processed {total_days} days, {total_articles} articles so far",
                }

        yield {
            "type": "log", "level": "info",
            "msg": f"Done — {total_days} days scanned, {total_articles} articles collected",
        }
