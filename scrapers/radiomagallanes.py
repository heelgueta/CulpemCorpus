"""
Radio Magallanes — radiomagallanes.cl
robots.txt: only /wp-admin/ blocked. No crawl-delay. wp-sitemap.xml declared.
"""
from .wordpress import WordPressScraper


class RadioMagallanesScraper(WordPressScraper):
    name = "Radio Magallanes"
    base_url = "https://radiomagallanes.cl"
    min_delay = 1.0
