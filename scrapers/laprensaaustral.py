"""
La Prensa Austral — laprensaaustral.cl
robots.txt: only /wp-admin/ blocked. No crawl-delay.
"""
from .wordpress import WordPressScraper


class LaPrensaAustralScraper(WordPressScraper):
    name = "La Prensa Austral"
    base_url = "https://laprensaaustral.cl"
    min_delay = 0.5
