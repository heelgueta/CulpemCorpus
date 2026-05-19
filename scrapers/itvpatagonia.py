"""
ITV Patagonia — itvpatagonia.com
robots.txt: Cloudflare content-signal framework; blocks AI crawlers by UA name.
WP REST API returns 403 with our default UA but 200 with a standard browser UA.
use_browser_ua=True switches to a Chrome UA for all requests to this site.
"""
from .wordpress import WordPressScraper


class ItvPatagoniaScraper(WordPressScraper):
    name = "ITV Patagonia"
    base_url = "https://www.itvpatagonia.com"
    min_delay = 1.0
    use_browser_ua = True
