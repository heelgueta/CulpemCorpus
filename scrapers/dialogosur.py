"""
Diálogo Sur — dialogosur.cl
robots.txt: Crawl-delay: 5. Multiple sitemaps including Google News.
"""
from .wordpress import WordPressScraper


class DialogoSurScraper(WordPressScraper):
    name = "Diálogo Sur"
    base_url = "https://dialogosur.cl"
    min_delay = 5.0
