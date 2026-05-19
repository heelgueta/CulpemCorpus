"""
Pepe Noticias — pepenoticias.cl
robots.txt: no restrictions (Disallow: empty). Sitemap index declared.
"""
from .wordpress import WordPressScraper


class PepeNoticiasScraper(WordPressScraper):
    name = "Pepe Noticias"
    base_url = "https://pepenoticias.cl"
    min_delay = 1.0
