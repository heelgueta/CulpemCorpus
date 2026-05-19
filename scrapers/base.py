import time
import re
import logging
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "CulpemCorpus/1.0 (academic corpus research, Magallanes media; "
        "contact: culpem@research.local)"
    ),
    "Accept-Language": "es-CL,es;q=0.9,en;q=0.5",
}

ARTICLE_FIELDS = ["source", "date", "title", "url", "body_text", "section"]


class BaseScraper:
    name = "Base"
    base_url = ""
    min_delay = 1.0  # override per scraper to respect robots.txt

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def get(self, url, delay=1.5, **kwargs):
        actual_delay = max(delay, self.min_delay)
        time.sleep(actual_delay)
        try:
            r = self.session.get(url, timeout=20, **kwargs)
            r.raise_for_status()
            return r
        except requests.exceptions.HTTPError as e:
            logger.warning("HTTP %s: %s", e.response.status_code, url)
            return None
        except requests.RequestException as e:
            logger.warning("Failed: %s — %s", url, e)
            return None

    def clean_html(self, html_or_soup):
        """Strip tags and collapse to a single-line string.

        Single-line output keeps CSV cells intact regardless of quote content.
        JSONL consumers can treat whitespace runs as paragraph breaks if needed.
        """
        if isinstance(html_or_soup, str):
            soup = BeautifulSoup(html_or_soup, "lxml")
        else:
            soup = html_or_soup
        for tag in soup(["script", "style", "nav", "header", "footer",
                         "aside", "figure", "figcaption", "iframe", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator=" ")
        # Collapse all whitespace (spaces, tabs, newlines) to single space
        return re.sub(r"\s+", " ", text).strip()

    def in_date_range(self, date_str, date_from, date_to):
        if not date_str:
            return True
        d = date_str[:10]
        if date_from and d < date_from[:10]:
            return False
        if date_to and d > date_to[:10]:
            return False
        return True

    def run(self, query="", date_from="", date_to="", delay=1.5):
        raise NotImplementedError
