"""
Radio Polar — radiopolar.com
STATUS: Not scrape-able without a headless browser.

Technical findings (2026-05-19):
- Next.js frontend backed by a proprietary headless CMS ("Más Medios").
- Article listing requires JavaScript execution (JS "Load More", no paginated HTML).
- No RSS feed, no sitemap — every feed/sitemap URL returns the homepage HTML.
- The backend CMS API (Google Cloud Run) returns 401 for the public app token.
  The token in the page is only scoped for read access to template/layout data,
  not the content/post listing API.
- Individual article pages contain full content in __NEXT_DATA__ → route.post,
  but without a slug list there is no way to discover which articles exist.

To add Radio Polar support: use Playwright to render the homepage, click
"Cargar más" repeatedly, collect slugs, then fetch each slug's
/_next/data/{buildId}/{slug}.json for the article content.
"""


class RadioPolarScraper:
    name = "Radio Polar"
    base_url = "https://www.radiopolar.com"

    def run(self, query="", date_from="", date_to="", delay=1.5):
        yield {
            "type": "log", "level": "warn",
            "msg": (
                "Radio Polar is not supported: its listing requires JavaScript rendering "
                "and the content API requires authenticated access. "
                "See scrapers/radiopolar.py for details."
            ),
        }
