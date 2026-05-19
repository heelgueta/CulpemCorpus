# 🦊 CulpemCorpus

Local web app for scraping news articles from Magallanes regional media.
Named after the *culpeo magallánico* (Lycalopex culpaeus) — a digital sniffer that explores and captures texts for academic and creative analysis.

## Active sources

| Site | Method | Body text | Notes |
|---|---|---|---|
| [La Prensa Austral](https://laprensaaustral.cl) | WP REST API | Full article | |
| [El Pingüino](https://elpinguino.com) | JSON API (discovery) + article page (body) | Full article | Date API lists articles; each article page fetched for `.sit3-single-body` |
| [El Magallánico](https://elmagallanico.com) | WP REST API | Full article | |
| [Ovejero Noticias](https://www.ovejeronoticias.cl) | WP REST API | Full article | Blocks `ClaudeBot` UA; our UA is fine |
| [SOS Magallanes](https://www.sosmagallanes.cl) | WP REST API | Full article | Blocks `ClaudeBot` UA; our UA is fine |
| [Radio Magallanes](https://radiomagallanes.cl) | WP REST API | Full article | |
| [Pepe Noticias](https://pepenoticias.cl) | WP REST API | Full article | |
| [Diálogo Sur](https://dialogosur.cl) | WP REST API | Full article | `Crawl-delay: 5` respected |
| [ITV Patagonia](https://www.itvpatagonia.com) | WP REST API | Full article | Blocks non-browser UAs; uses browser UA |

All scraping respects robots.txt and uses a configurable delay (default 1.5 s).

## Setup

```bash
pip install -r requirements.txt
python3 app.py
# Open http://localhost:5001
```

## Modes

**Search** — query string + optional date range → articles matching the query  
**Bulk** — date range only → all articles in that period (El Pingüino requires a date range)

## Output fields

```
source, date, title, url, body_text, section
```

`body_text` is a flat single-line string (whitespace-collapsed). CSV uses UTF-8 BOM so it opens cleanly in Excel/Numbers. JSONL is one object per line.

### R (quanteda / tidytext)

```r
library(readr)
corpus <- read_csv("output/culpem_XXXXX.csv")
# or for JSONL:
library(jsonlite)
corpus <- stream_in(file("output/culpem_XXXXX.jsonl"))
```

### Python (spaCy / sklearn)

```python
import pandas as pd
df = pd.read_csv("output/culpem_XXXXX.csv")
# or
df = pd.read_json("output/culpem_XXXXX.jsonl", lines=True)
```

## Project structure

```
app.py                     Flask server (SSE progress + CSV/JSONL download)
scrapers/
  base.py                  Session, delay, HTML cleaning helpers
  wordpress.py             Shared WordPressScraper base class (all WP sources use this)
  laprensaaustral.py       WP
  elmagallanico.py         WP
  ovejeronoticias.py       WP
  sosmagallanes.py         WP
  radiomagallanes.py       WP
  pepenoticias.py          WP
  dialogosur.py            WP (crawl-delay 5s)
  itvpatagonia.py          WP (browser UA)
  elpinguino.py            JSON API scraper (date-iterating)
  radiopolar.py            stub — not supported (see below)
templates/index.html       Single-page UI
output/                    Generated files (gitignored)
```

---

## Unsupported source: Radio Polar

**Status:** disabled — not scrape-able without a headless browser.

**Technical findings (investigated 2026-05-19):**

- Site is a **Next.js frontend** backed by a proprietary headless CMS called *Más Medios* (hosted on Google Cloud Run: `officeapp-mspress-web-functions-production-ckv3wpf4tq-ue.a.run.app`).
- **No RSS feed, no sitemap** — every feed/sitemap path (`/feed/`, `/sitemap.xml`, `/rss.xml`, etc.) redirects to the homepage HTML.
- **Article listing is JS-rendered**: the homepage uses a "Cargar más" (load more) AJAX pattern. There are no paginated server-rendered listing pages.
- **The CMS API requires authenticated access**: the public app token embedded in the page is scoped only for template/layout reads. POST/GET to the content API (`/api/posts`, `/api/routes`, etc.) returns HTTP 401.
- Individual article pages DO contain full article data in `__NEXT_DATA__` → `route.post` (title, body, date) and are fetchable via `/_next/data/{buildId}/{slug}.json` — but **there is no server-accessible way to enumerate which slugs exist** without first rendering the listing with JavaScript.

**To add Radio Polar support:** use [Playwright](https://playwright.dev/) to render the homepage, click "Cargar más" repeatedly until the desired date range is covered, collect slugs, then fetch each article via `/_next/data/{buildId}/{slug}.json`.

---

## Needs exploring: El Magallanews

**Status:** not implemented — blocked at investigation stage.

**Findings:** Cloudflare blocks automated access at the network level. The WordPress REST API returns 404 (not exposed or disabled). Even with a standard browser User-Agent, the API endpoint is unreachable. The site is likely behind a Cloudflare WAF that requires JS challenge completion. Needs further investigation (possibly Playwright + Cloudflare bypass, or manual cookie extraction).

---

## Notes

- Output files are saved to `output/` and served via `/download/<filename>`.
- Failed URLs are logged but do not abort the run.
- For large bulk jobs (e.g. all of 2025), El Pingüino makes ~365 API calls — around 6 min at 1 s delay.
- Diálogo Sur enforces a 5-second crawl delay; large date ranges will be slow.
- To add a new WP-based source: create a file in `scrapers/` that subclasses `WordPressScraper`, set `name`, `base_url`, and `min_delay`, then register it in `scrapers/__init__.py` and `templates/index.html`.
