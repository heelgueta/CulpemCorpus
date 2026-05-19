"""
El Magallánico — elmagallanico.com
robots.txt: only /wp-admin/ blocked. No crawl-delay. Sitemap declared.
"""
from .wordpress import WordPressScraper


class ElMagallanicoScraper(WordPressScraper):
    name = "El Magallánico"
    base_url = "https://elmagallanico.com"
    min_delay = 1.0
