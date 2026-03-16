# newsloupe — HN Data Source Options

Reference document for alternative data sources that can be plugged into the `HNSource` abstraction layer. Only Algolia is implemented in v1. This doc exists so we know exactly what's available if we ever need to swap.

---

## Currently Implemented

### Algolia HN Search API

- **URL:** `https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=30`
- **Auth:** None required
- **Format:** JSON
- **Requests for 30 front page stories:** 1
- **Metadata returned:** title, url, author, points, num_comments, created_at, objectID
- **Feed types available:**
  - `tags=front_page` — current front page
  - `tags=show_hn` — Show HN
  - `tags=ask_hn` — Ask HN
  - `tags=story` — all stories
  - `tags=comment` — all comments
  - Combinable with `numericFilters` (e.g., `points>50`, `num_comments>10`)
  - Combinable with `created_at_i` for time-windowed queries
  - `search_by_date` endpoint for chronological ordering
- **Rate limit:** ~10,000 requests/hour (undocumented but generous)
- **Max results:** 1,000 per query (paginated via `page` param, `hitsPerPage` max 1,000)
- **Strengths:** One request, structured JSON, rich filtering and search, full metadata
- **Risks:** GitHub repo archived Feb 2026, occasional index staleness, maintenance now opaque (private repo)

---

## Not Yet Implemented — Future Options

### Official Firebase API

- **Base URL:** `https://hacker-news.firebaseio.com/v0/`
- **Auth:** None required
- **Format:** JSON
- **Requests for 30 front page stories:** 31 (1 for ID list + 30 individual item fetches)
- **Feed endpoints:**
  - `/topstories.json` — top 500 story IDs
  - `/newstories.json` — newest 500 story IDs
  - `/beststories.json` — best 500 story IDs
  - `/askstories.json` — up to 200 Ask HN IDs
  - `/showstories.json` — up to 200 Show HN IDs
  - `/jobstories.json` — job post IDs
- **Per-item endpoint:** `/item/{id}.json` — returns title, url, by, score, descendants, time, type, kids
- **Rate limit:** None documented
- **Strengths:** Canonical data source run by HN itself, will never go away, supports SSE for real-time streaming, gives access to "newest" and "best" feeds that Algolia doesn't expose as tags
- **Weaknesses:** N+1 request pattern is slow and verbose, no search or filtering, no way to get front page specifically (topstories ≠ front page — it's the top 500 by ranking score, not just what's currently displayed)
- **Implementation notes:** Would benefit from `asyncio`/`aiohttp` for concurrent item fetches. Could batch 30 requests in parallel to keep latency reasonable (~1-2 seconds).

---

### hnrss.org

- **URL:** `https://hnrss.org/frontpage.jsonfeed`
- **Auth:** None required
- **Format:** RSS (default), Atom (`.atom`), or JSON Feed (`.jsonfeed`)
- **Requests for front page:** 1
- **Available feeds:**
  - `/frontpage` — front page stories
  - `/newest` — all new stories
  - `/ask` — Ask HN
  - `/show` — Show HN
  - `/jobs` — job posts
  - `/best` — best stories
  - `/submitted?id=USERNAME` — specific user's posts
  - `/threads?id=USERNAME` — specific user's comments
  - `/whoishiring/jobs` — Who is Hiring thread comments
- **Filtering:**
  - `?points=N` — minimum points
  - `?comments=N` — minimum comments
  - `?q=KEYWORD` — keyword search in titles
  - `?q=KEYWORD&search_attrs=url` — search in URLs
  - `?count=N` — number of items (max 100)
- **Strengths:** Single request, JSON output available, rich filtering, nice feed variety (especially whoishiring), easy to consume
- **Weaknesses:** Built on Algolia under the hood, so shares the same data freshness risks. Hardcoded 100-entry limit. JSON Feed format is less battle-tested than the RSS output. Less metadata than raw Algolia (no objectID in the feed, would need to extract from URLs).

---

### Direct HTML Scraping

- **URL:** `https://news.ycombinator.com/`
- **Auth:** None required
- **Format:** HTML (parse with BeautifulSoup)
- **Requests for front page:** 1
- **What you can extract:** title, url, HN item ID, points, comment count, author, age
- **Available pages:**
  - `/` — front page (30 stories)
  - `/newest` — newest submissions
  - `/ask` — Ask HN
  - `/show` — Show HN
  - `/jobs` — jobs
  - `/news?p=2` — pagination
- **Strengths:** Completely independent of any third-party service, single request, gets exactly what's on the page
- **Weaknesses:** Fragile if HN changes markup (though they rarely do), requires HTML parsing, no search/filtering built in, harder to get metadata cleanly
- **Implementation notes:** HN's HTML is a simple `<table>` layout. Titles are in `.titleline > a`, metadata in `.subtext`. BeautifulSoup is the natural parser. Consider keeping a simple regex fallback since the markup is so predictable.

---

### HN Built-in RSS

- **URL:** `https://news.ycombinator.com/rss`
- **Auth:** None required
- **Format:** RSS/XML
- **Requests:** 1
- **Strengths:** Official, simple, built into HN itself
- **Weaknesses:** Minimal — only returns title and link, no points, no comment count, no author, no filtering. Essentially the least useful option for a recommendation engine. Only worth considering as a last-resort fallback.

---

## Comparison Matrix

| Source | Requests | Format | Metadata | Filtering | Independence | Risk |
|---|---|---|---|---|---|---|
| **Algolia** | 1 | JSON | Full | Rich | Third-party | Repo archived, staleness |
| **Firebase** | N+1 | JSON | Full | None | Official (YC) | Slow, verbose |
| **hnrss.org** | 1 | JSON/RSS | Moderate | Good | Third-party (uses Algolia) | Depends on Algolia |
| **Scraping** | 1 | HTML | Parseable | None | Fully independent | Markup changes |
| **Built-in RSS** | 1 | RSS | Minimal | None | Official (YC) | Too limited |

---

## Recommended Fallback Order

If Algolia becomes unreliable:

1. **hnrss.org** (`.jsonfeed`) — easiest swap, similar data, one request
2. **Scraping** — fully independent, one request, requires parser
3. **Firebase API** — canonical source, but needs async batching for acceptable speed
4. **Built-in RSS** — last resort, insufficient metadata

Each of these would be implemented as a new class conforming to the `HNSource` interface defined in `sources/base.py`, selectable via a CLI flag in the `newsloupe` CLI or `serve.py`.
