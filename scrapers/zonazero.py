"""
Zona Zero — zonazero.cl
robots.txt: /wp-admin/ and WooCommerce dirs blocked. No crawl-delay.
WP REST API confirmed. 7,622 articles from 2021-04-26.
"""
from .wordpress import WordPressScraper


class ZonaZeroScraper(WordPressScraper):
    name = "Zona Zero"
    base_url = "https://zonazero.cl"
    min_delay = 1.0
