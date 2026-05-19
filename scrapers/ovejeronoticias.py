"""
Ovejero Noticias — ovejeronoticias.cl
robots.txt: blocks ClaudeBot and other AI crawlers by name; general crawling allowed.
Our CulpemCorpus UA is not blocked. No crawl-delay.
"""
from .wordpress import WordPressScraper


class OvejeroNoticiasScraper(WordPressScraper):
    name = "Ovejero Noticias"
    base_url = "https://www.ovejeronoticias.cl"
    min_delay = 1.0
