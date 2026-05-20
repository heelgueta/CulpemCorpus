"""
El Pingüino — elpinguino.com

Discovery: Internal JSON API GET /v2/home/search/{YYYY-MM-DD}
  → returns all articles for a date with title, excerpt, category, slug.
  No text-search endpoint exists — only day-by-day iteration.

Search mode optimisation (parallel discovery):
  Daily API calls are tiny JSON (~1 KB). No crawl-delay in robots.txt.
  In search mode we fan out up to DISCOVERY_WORKERS concurrent threads at
  DISCOVERY_DELAY seconds each. Wall-clock for 6000 days drops from ~100 min
  to ~3 min. Article page fetches (heavier HTML) stay sequential at 1 s.

Bulk mode: sequential at the user-set delay (full pages for every article).

Full body: GET /noticia/{YYYY}/{MM}/{DD}/{slug}
  → single-article page, body in .sit3-single-body (their CSS typo, not ours).

Encoding: server mis-declares UTF-8; pass r.content to lxml to read <meta charset>.
"""
import re
import queue
import threading
import time
import logging
from datetime import date, timedelta
from bs4 import BeautifulSoup

import requests

from .base import BaseScraper, HEADERS

logger = logging.getLogger(__name__)

DATE_API = "https://elpinguino.com/v2/home/search"
BASE     = "https://www.elpinguino.com"

DISCOVERY_WORKERS = 10
DISCOVERY_DELAY   = 0.3


def build_url(item, date_str):
    """
    Correct URL for an El Pingüino article.
    Before 2014-04-01: /noticias/{ID}  (slug is empty, ID field present)
    After  2014-04-01: /noticia/YYYY/MM/DD/{slug}
    """
    slug = item.get("post_slug", "")
    if slug:
        yyyy, mm, dd = date_str[:4], date_str[5:7], date_str[8:10]
        return f"{BASE}/noticia/{yyyy}/{mm}/{dd}/{slug}"
    else:
        aid = item.get("ID", item.get("id", ""))
        if aid:
            return f"{BASE}/noticias/{aid}"
        return f"{BASE}/noticias/unknown-{date_str}-{item.get('post_title','')[:20]}"


def iter_dates(date_from, date_to):
    try:
        d   = date.fromisoformat(date_from)
        end = date.fromisoformat(date_to)
    except (ValueError, TypeError):
        return
    while d <= end:
        yield d.isoformat()
        d += timedelta(days=1)


class ElPinguinoScraper(BaseScraper):
    name      = "El Pingüino"
    base_url  = BASE
    min_delay = 1.0

    # ------------------------------------------------------------------ date API (single)

    def _fetch_day_raw(self, session, date_str, delay=DISCOVERY_DELAY):
        """Fetch one date via a provided requests.Session (thread-safe call)."""
        time.sleep(delay)
        try:
            r = session.get(f"{DATE_API}/{date_str}", timeout=15)
            if r.status_code != 200:
                return date_str, []
            data = r.json()
            if data.get("info", {}).get("api_code") == 404:
                return date_str, []
            return date_str, data.get("result", [])
        except Exception as e:
            logger.warning("EP date API failed %s: %s", date_str, e)
            return date_str, []

    # ------------------------------------------------------------------ parallel discovery

    def _discover_parallel(self, date_from, date_to, query_lower, log_q):
        """
        Fan out date API calls across DISCOVERY_WORKERS threads.
        Returns a list of (date_str, item) tuples for articles passing the query filter.
        Items are in chronological order.
        """
        all_dates = list(iter_dates(date_from, date_to))
        total     = len(all_dates)
        log_q.put(f"Discovery: {total} days to scan ({DISCOVERY_WORKERS} parallel workers)")

        results   = {}   # date_str → [items]
        lock      = threading.Lock()
        idx       = [0]  # shared counter protected by lock

        def worker():
            # Each worker gets its own session so connections don't share state
            session = requests.Session()
            session.headers.update(HEADERS)
            while True:
                with lock:
                    if idx[0] >= total:
                        return
                    date_str = all_dates[idx[0]]
                    idx[0] += 1
                d, items = self._fetch_day_raw(session, date_str)
                with lock:
                    results[d] = items

        threads = [threading.Thread(target=worker, daemon=True)
                   for _ in range(DISCOVERY_WORKERS)]
        for t in threads:
            t.start()

        # Report progress while threads run
        done_last = 0
        while any(t.is_alive() for t in threads):
            time.sleep(2)
            with lock:
                done = len(results)
            if done != done_last:
                log_q.put(f"  Discovery: {done}/{total} days scanned…")
                done_last = done

        for t in threads:
            t.join()

        # Reassemble in chronological order and apply query filter
        matches = []
        for date_str in all_dates:
            for item in results.get(date_str, []):
                if query_lower:
                    haystack = f"{item.get('post_title','')} {item.get('post_excerpt','')}".lower()
                    if query_lower not in haystack:
                        continue
                matches.append((date_str, item))

        log_q.put(f"Discovery done — {len(matches)} candidate articles from {total} days")
        return matches

    # ------------------------------------------------------------------ article page

    def _fetch_body(self, url, delay):
        r = self.get(url, delay=delay)
        if not r:
            return None

        soup = BeautifulSoup(r.content, "lxml")

        title_el = soup.select_one(".site3-single h1")
        title    = title_el.get_text(strip=True) if title_el else ""

        cat_el  = soup.select_one(".meta.cat")
        section = cat_el.get_text(strip=True) if cat_el else ""

        date_str = ""
        for el in soup.select(".site3-meta-title .meta"):
            text = el.get_text(" ", strip=True)
            m = re.search(r"(\d{2})/(\d{2})/(\d{4})", text)
            if m:
                date_str = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
                break

        body_el   = soup.select_one(".sit3-single-body")
        body_text = ""
        if body_el:
            for tag in body_el(["script", "style", "div"]):
                tag.decompose()
            paragraphs = [p.get_text(strip=True) for p in body_el.find_all("p")
                          if p.get_text(strip=True)]
            body_text = " ".join(paragraphs)

        return title, date_str, section, body_text

    # ------------------------------------------------------------------ run

    def run(self, query="", date_from="", date_to="", delay=1.5):
        if not date_from or not date_to:
            yield {"type": "log", "level": "warn",
                   "msg": "El Pingüino requires a date range — use From / To fields"}
            return

        query_lower    = query.lower().strip()
        is_search_mode = bool(query_lower)

        # ---------- SEARCH MODE: parallel discovery, then fetch only matches ----------
        if is_search_mode:
            log_q = queue.Queue()
            # Run parallel discovery in a background thread so we can yield logs
            candidates = [None]
            def run_discovery():
                candidates[0] = self._discover_parallel(
                    date_from, date_to, query_lower, log_q)

            disc_thread = threading.Thread(target=run_discovery, daemon=True)
            disc_thread.start()

            while disc_thread.is_alive() or not log_q.empty():
                try:
                    msg = log_q.get(timeout=0.5)
                    yield {"type": "log", "level": "info", "msg": msg}
                except queue.Empty:
                    pass
            disc_thread.join()

            total_articles = 0
            for date_str, item in (candidates[0] or []):
                api_title  = item.get("post_title", "")
                api_excerpt = item.get("post_excerpt", "")
                url = build_url(item, date_str)

                result = self._fetch_body(url, delay=max(delay, self.min_delay))
                if result:
                    title, art_date, section, body_text = result
                else:
                    title, art_date, section, body_text = (
                        api_title, date_str, item.get("post_category", ""), api_excerpt)

                yield {
                    "type": "article",
                    "data": {
                        "source":    "El Pingüino",
                        "date":      art_date or date_str,
                        "title":     title or api_title,
                        "url":       url,
                        "body_text": body_text or api_excerpt,
                        "section":   section or item.get("post_category", ""),
                    },
                }
                total_articles += 1

            yield {"type": "log", "level": "info",
                   "msg": f"Done — {total_articles} articles collected"}

        # ---------- BULK MODE: sequential, one day at a time ----------
        else:
            total_days, total_articles = 0, 0
            for date_str in iter_dates(date_from, date_to):
                total_days += 1
                _, items = self._fetch_day_raw(self.session, date_str, delay=max(delay, self.min_delay))

                for item in items:
                    api_title   = item.get("post_title", "")
                    api_excerpt = item.get("post_excerpt", "")
                    url = build_url(item, date_str)

                    result = self._fetch_body(url, delay=max(delay, self.min_delay))
                    if result:
                        title, art_date, section, body_text = result
                    else:
                        title, art_date, section, body_text = (
                            api_title, date_str, item.get("post_category", ""), api_excerpt)

                    yield {
                        "type": "article",
                        "data": {
                            "source":    "El Pingüino",
                            "date":      art_date or date_str,
                            "title":     title or api_title,
                            "url":       url,
                            "body_text": body_text or api_excerpt,
                            "section":   section or item.get("post_category", ""),
                        },
                    }
                    total_articles += 1

                if total_days % 10 == 0:
                    yield {"type": "log", "level": "info",
                           "msg": f"  {total_days} days, {total_articles} articles so far"}

            yield {"type": "log", "level": "info",
                   "msg": f"Done — {total_days} days scanned, {total_articles} articles collected"}
