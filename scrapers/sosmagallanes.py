"""
SOS Magallanes — sosmagallanes.cl
robots.txt: blocks ClaudeBot and other AI crawlers by name; general crawling allowed.
Our CulpemCorpus UA is not blocked. No crawl-delay.
"""
from .wordpress import WordPressScraper


class SosMagallanesScraper(WordPressScraper):
    name = "SOS Magallanes"
    base_url = "https://www.sosmagallanes.cl"
    min_delay = 1.0
