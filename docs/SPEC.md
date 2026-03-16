# newsloupe — Implementation Spec

> **Purpose:** This document is a complete implementation specification for a coding agent. It contains everything needed to build the project from scratch: architecture, file-by-file specs, data formats, algorithms, CLI behavior, and test expectations.

---

## 1. Project Overview

**newsloupe** is a Python CLI tool that scores Hacker News front page articles against a personal interest profile using two methods (TF-IDF and sentence embeddings) side by side. Interests come from a manually maintained JSON file of articles the user found interesting anywhere on the web. Output is a ranked terminal table (default) or a self-contained HTML report (`--html` flag). A separate FastAPI web server (`serve.py`) can serve the report in a browser with a re-score button.

**Key design principles:**
- Local-first: no API keys, no accounts, no hosted services (except the public Algolia HN API)
- Fast: ~1.5 seconds on a warm run
- Comparison-oriented: both scoring methods shown side by side so the user can evaluate which works better
- Abstracted data source: HN data fetching is behind an interface so backends can be swapped

---

## 2. Project Structure

```
newsloupe/
├── newsloupe.py               # CLI entry point
├── serve.py                   # FastAPI web server entry point
├── sources/
│   ├── __init__.py
│   ├── base.py                # abstract HNSource interface
│   └── algolia.py             # Algolia API implementation
├── scorers/
│   ├── __init__.py
│   ├── tfidf.py               # TF-IDF + cosine similarity scorer
│   └── embeddings.py          # sentence-transformers scorer
├── output/
│   ├── __init__.py
│   ├── terminal.py            # rich table renderer
│   └── html.py                # self-contained HTML report generator
├── core.py                    # shared scoring pipeline (used by CLI and server)
├── cache.py                   # embedding cache manager
├── interests.json             # sample/default interests file
├── requirements.txt
├── tests/
│   ├── test_sources.py
│   ├── test_scorers.py
│   ├── test_cache.py
│   └── test_output.py
└── README.md
```

---

## 3. Dependencies

```
# requirements.txt
requests>=2.31.0
scikit-learn>=1.3.0
sentence-transformers>=2.2.0
rich>=13.0.0
numpy>=1.24.0
fastapi>=0.110.0
uvicorn>=0.29.0
```

All installable via `pip install -r requirements.txt`. No API keys. The sentence-transformers model (`all-MiniLM-L6-v2`, ~80MB) downloads automatically on first run.

---

## 4. Data Formats

### 4.1 Interest File (`interests.json`)

```json
[
  {
    "title": "How Rust handles memory safety without a GC",
    "url": "https://example.com/rust-memory"
  },
  {
    "title": "Lessons from scaling Postgres to 1TB+",
    "url": "https://example.com/pg-scale"
  }
]
```

- Array of objects. Each object must have `title` (string, required) and `url` (string, required).
- `title` is the primary scoring signal. `url` is stored for reference but not used in v1 scoring.
- File is read fresh each run. The user maintains it manually.
- Minimum recommended corpus size: 20-30 articles for meaningful scores.

### 4.2 Embedding Cache (`.embeddings_cache.json`)

```json
{
  "model": "all-MiniLM-L6-v2",
  "embeddings": {
    "How Rust handles memory safety without a GC": [0.023, -0.041, ...],
    "Lessons from scaling Postgres to 1TB+": [0.018, 0.055, ...]
  }
}
```

- Keys are article titles (exact match).
- Values are embedding vectors as arrays of floats.
- `model` field tracks which model was used. If the model changes, the entire cache is invalidated.
- Auto-generated. Never manually edited.
- On each run: load cache, compute embeddings only for titles not in cache, remove stale entries for titles no longer in interests, write updated cache.

### 4.3 HN Story (internal data structure)

```python
@dataclass
class HNStory:
    title: str
    url: str           # article URL (external link)
    hn_url: str        # HN discussion URL
    object_id: str     # HN item ID
    points: int
    num_comments: int
    author: str
    created_at: str    # ISO timestamp
```

This is the normalized format returned by all `HNSource` implementations.

### 4.4 Scored Result (internal data structure)

```python
@dataclass
class ScoredStory:
    story: HNStory
    tfidf_score: float      # 0.0 to 1.0
    embedding_score: float  # 0.0 to 1.0
    delta: float            # embedding_score - tfidf_score
    max_score: float        # max(tfidf_score, embedding_score)
```

---

## 5. File-by-File Implementation Specs

### 5.1 `sources/base.py` — Abstract HN Source

```python
from abc import ABC, abstractmethod

class HNSource(ABC):
    @abstractmethod
    def fetch_stories(self, count: int = 30) -> list[HNStory]:
        """Fetch stories from HN. Returns normalized HNStory list."""
        pass
```

That's it. One method. Each backend implements this and maps its response format to `HNStory`.

### 5.2 `sources/algolia.py` — Algolia Implementation

**Endpoint:** `https://hn.algolia.com/api/v1/search`

**Parameters:**
- `tags` — feed type, default `front_page`. Also supports `show_hn`, `ask_hn`, `story`.
- `hitsPerPage` — number of results, default 30.

**Constructor takes:**
- `feed: str = "front_page"` — which Algolia tag to use.

**Implementation:**
1. Make GET request to `https://hn.algolia.com/api/v1/search?tags={feed}&hitsPerPage={count}`
2. Parse JSON response. Stories are in `response["hits"]`.
3. Map each hit to `HNStory`:
   - `title` = `hit["title"]`
   - `url` = `hit["url"]` or `f"https://news.ycombinator.com/item?id={hit['objectID']}"` if url is null (self-posts)
   - `hn_url` = `f"https://news.ycombinator.com/item?id={hit['objectID']}"`
   - `object_id` = `hit["objectID"]`
   - `points` = `hit.get("points", 0)`
   - `num_comments` = `hit.get("num_comments", 0)`
   - `author` = `hit.get("author", "")`
   - `created_at` = `hit.get("created_at", "")`
4. Return list of `HNStory`.

**Error handling:**
- Timeout: 10 seconds. Raise clear error message.
- Non-200 status: raise with status code and response body.
- Empty hits: return empty list (not an error).

### 5.3 `scorers/tfidf.py` — TF-IDF Scorer

**Class:** `TfidfScorer`

**Method:** `score(interest_titles: list[str], story_titles: list[str]) -> list[float]`

**Algorithm:**
1. Build a combined corpus: `interest_titles + story_titles`.
2. Fit `TfidfVectorizer(stop_words='english', ngram_range=(1, 2))` on the full corpus.
3. Transform to get TF-IDF matrix.
4. Split the matrix back into interest vectors (first N rows) and story vectors (remaining rows).
5. For each story vector, compute cosine similarity against all interest vectors using `cosine_similarity`.
6. The score for each story is the **maximum similarity** to any single interest.
7. Return list of scores (one per story), in the same order as `story_titles`.

**Notes:**
- Scores are naturally in 0.0-1.0 range (cosine similarity).
- Using bigrams (`ngram_range=(1, 2)`) helps catch compound terms like "machine learning" or "distributed systems".
- No caching needed — fast enough to recompute every run (<50ms for typical corpus sizes).

### 5.4 `scorers/embeddings.py` — Embedding Scorer

**Class:** `EmbeddingScorer`

**Constructor:**
- `model_name: str = "all-MiniLM-L6-v2"` — which sentence-transformers model to use.
- Loads the model on init. First run downloads the model (~80MB).

**Methods:**

`encode(texts: list[str]) -> np.ndarray`
- Wraps `model.encode(texts, show_progress_bar=False)`.
- Returns 2D numpy array, shape `(len(texts), embedding_dim)`.

`score(interest_embeddings: np.ndarray, story_titles: list[str]) -> list[float]`
1. Encode `story_titles` to get story embeddings.
2. Compute cosine similarity matrix between story embeddings and interest embeddings using `cosine_similarity` from sklearn.
3. For each story, the score is the **maximum similarity** to any single interest embedding.
4. Return list of scores (one per story).

**Notes:**
- Interest embeddings are pre-computed and cached (see `cache.py`). They are passed in, not computed here.
- Story embeddings are computed fresh each run (only 30 titles, ~200ms).
- Scores are naturally in 0.0-1.0 range.

### 5.5 `cache.py` — Embedding Cache Manager

**Class:** `EmbeddingCache`

**Constructor:**
- `cache_path: str = ".embeddings_cache.json"`
- `model_name: str = "all-MiniLM-L6-v2"`

**Methods:**

`load() -> dict[str, list[float]]`
- Load cache file if it exists.
- If `model` field doesn't match current `model_name`, return empty dict (full invalidation).
- Return the `embeddings` dict (title -> vector).

`save(embeddings: dict[str, list[float]])`
- Write `{"model": model_name, "embeddings": embeddings}` to cache file.
- Use `json.dump` with no extra formatting (keep file small).

`get_stale_and_new(cached: dict, current_titles: list[str]) -> tuple[list[str], list[str]]`
- `stale`: titles in cache but not in `current_titles` (to be removed).
- `new`: titles in `current_titles` but not in cache (to be computed).
- Returns `(stale, new)`.

**Usage pattern in main:**
```python
cache = EmbeddingCache()
cached_embeddings = cache.load()
stale, new = cache.get_stale_and_new(cached_embeddings, interest_titles)

# Remove stale
for title in stale:
    del cached_embeddings[title]

# Compute new
if new:
    new_vectors = embedding_scorer.encode(new)
    for title, vec in zip(new, new_vectors):
        cached_embeddings[title] = vec.tolist()

cache.save(cached_embeddings)

# Build numpy array in same order as interest_titles
interest_embeddings = np.array([cached_embeddings[t] for t in interest_titles])
```

### 5.6 `output/terminal.py` — Terminal Table Renderer

**Function:** `render_terminal(results: list[ScoredStory], sort_by: str = "max")`

Uses `rich` library.

**Behavior:**
1. Sort `results` by the specified field (`max_score`, `tfidf_score`, or `embedding_score`), descending.
2. Print a header: `"HN Front Page — Scored Against Your Interests ({date})"`.
3. Print a `rich.table.Table` with columns:
   - `#` — rank (1-indexed)
   - `Title` — story title, truncated to 60 chars if needed
   - `TF-IDF` — score formatted to 2 decimal places
   - `Embed` — score formatted to 2 decimal places
   - `Δ` — delta formatted with sign (`+0.07` or `-0.03`)
   - `HN Link` — `hn_url`, truncated to 40 chars

**Color coding:**
- Scores ≥ 0.5: green
- Scores 0.25-0.49: yellow
- Scores < 0.25: dim/gray
- Delta column: green if positive, red if negative

### 5.7 `output/html.py` — HTML Report Generator

**Two functions sharing one template:**

`render_html_string(results: list[ScoredStory], sort_by: str = "max", last_updated: datetime = None, include_rescore_button: bool = False) -> str`
- Returns the full HTML as a string. Used by the web server.

`render_html(results: list[ScoredStory], output_path: str = "output.html", sort_by: str = "max")`
- Calls `render_html_string(results, sort_by, include_rescore_button=False)` and writes to file.
- Prints confirmation to stderr: `"HTML report written to {output_path}"`.
- Used by the CLI.

Generates a **single self-contained HTML file** with all CSS and JS inline. No external dependencies.

**Content:**
- Title/header with generation timestamp (uses `last_updated` if provided, otherwise `datetime.now()`)
- Conditional "Re-score" button (only when `include_rescore_button=True`, i.e. when served by FastAPI)
- Table with the same columns as terminal output, plus:
  - Title column is a clickable link to the article URL
  - HN Link column is a clickable link to the discussion page
  - Score cells have a background color gradient (green for high, white for low)
  - Small horizontal bar visualization inside each score cell
- JavaScript for client-side column sorting (click any header to sort)
- Responsive CSS that works on desktop and mobile

**Re-score button behavior (JS, inline):**
```javascript
// On button click:
// 1. Disable button, show "Scoring..." text
// 2. POST /rescore
// 3. On success: reload the page (GET / will serve fresh results)
// 4. On error: show error message, re-enable button
```

**Style:**
- Clean, minimal design. Light background, readable font (system font stack).
- Table with alternating row colors.
- Sticky header row.
- Re-score button: positioned top-right of the header area, subtle style, not prominent.
- Print-friendly (button hidden in print CSS).
### 5.8 `core.py` — Shared Scoring Pipeline

Both the CLI and web server need to run the same scoring logic. This module extracts that into a reusable function so neither has to duplicate it.

**Function:** `run_scoring(interests_path: str, feed: str, source: str, no_cache: bool) -> list[ScoredStory]`

**Steps:**
1. Load and validate interests from `interests_path`.
2. Initialize HN source (Algolia) with `feed`.
3. Fetch HN stories.
4. Initialize TF-IDF scorer.
5. Initialize embedding scorer (loads model).
6. Load/manage embedding cache (skip if `no_cache`).
7. Compute scores from both methods.
8. Build and return `list[ScoredStory]`.

This function does NOT handle output rendering — that's the caller's job (CLI renders to terminal/HTML file, server renders to HTTP response).

**Function:** `load_and_validate_interests(path: str) -> list[dict]`

Extracted validation logic so both CLI and server can share it:
1. Check file exists.
2. Parse JSON.
3. Validate non-empty array.
4. Validate each item has `title`.
5. Return list of interest dicts.
6. Raise `ValueError` with descriptive message on any failure.

### 5.9 `newsloupe.py` — CLI Entry Point

**Uses `argparse` for CLI parsing.**

**Arguments:**

| Flag | Short | Type | Default | Description |
|---|---|---|---|---|
| `--file` | `-f` | str | `interests.json` | Path to interests JSON file |
| `--top` | `-n` | int | `None` (all) | Show only top N results |
| `--sort-by` | `-s` | str | `max` | Sort by: `tfidf`, `embed`, `max` |
| `--threshold` | `-t` | float | `0.0` | Only show articles scoring above this |
| `--html` | | str (optional) | `output.html` | Generate HTML report. If flag given with no path, uses default. |
| `--json` | | flag | `False` | Output raw JSON to stdout |
| `--no-cache` | | flag | `False` | Force recompute all embeddings |
| `--source` | | str | `algolia` | HN data source (only `algolia` implemented) |
| `--feed` | | str | `front_page` | Algolia feed tag: `front_page`, `show_hn`, `ask_hn` |

**Main flow:**

```
1. Parse CLI arguments
2. Call core.run_scoring(interests_path, feed, source, no_cache)
   - Prints progress to stderr ("Fetching HN...", "Loading model...", etc.)
3. Apply --threshold filter (drop stories where max_score < threshold)
4. Apply --top limit (take first N after sorting)
5. Render output
   a. If --json: print JSON to stdout
   b. If --html: write HTML file AND print terminal table
   c. Default: print terminal table
```

**Timing:** Print total execution time to stderr at the end: `"Done in {elapsed:.1f}s"`.

### 5.10 `serve.py` — FastAPI Web Server

**Separate entry point.** Run with: `python serve.py` (which calls `uvicorn` internally) or `uvicorn serve:app`.

**CLI arguments (via argparse, parsed before uvicorn starts):**

| Flag | Short | Type | Default | Description |
|---|---|---|---|---|
| `--file` | `-f` | str | `interests.json` | Path to interests JSON file |
| `--feed` | | str | `front_page` | Algolia feed tag |
| `--port` | `-p` | int | `8000` | Port to serve on |
| `--host` | | str | `127.0.0.1` | Host to bind to |

**App state:**
- On startup, run an initial scoring pass and store results in memory.
- The app holds the current `list[ScoredStory]` and a `last_updated: datetime` timestamp.

**Routes:**

`GET /`
- Render the HTML report from the current in-memory results.
- Use `output/html.py`'s `render_html_string()` function (returns HTML as a string instead of writing to a file).
- Return as `text/html` response.
- The HTML includes a "Re-score" button (see updated HTML spec below).

`POST /rescore`
- Call `core.run_scoring(interests_path, feed, "algolia", no_cache=False)`.
- This runs synchronously (blocking). Since scoring takes ~1.5s, this is fine.
- Update the in-memory results and `last_updated` timestamp.
- Return `{"status": "ok", "last_updated": "...", "story_count": N}` as JSON.

`GET /api/results`
- Return the current scored results as JSON (same format as `--json` CLI output).
- Useful for debugging or if you ever want to consume results programmatically.

**Startup behavior:**
```python
import argparse
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI()

# Global state
state = {
    "results": [],
    "last_updated": None,
    "interests_path": "interests.json",
    "feed": "front_page",
}

@app.on_event("startup")
async def startup():
    # Run initial scoring
    state["results"] = await asyncio.to_thread(
        core.run_scoring, state["interests_path"], state["feed"], "algolia", False
    )
    state["last_updated"] = datetime.now()

if __name__ == "__main__":
    args = parse_args()
    state["interests_path"] = args.file
    state["feed"] = args.feed
    uvicorn.run(app, host=args.host, port=args.port)
```

**Notes:**
- `core.run_scoring` is CPU-bound (model inference), so wrap in `asyncio.to_thread` to not block the event loop during re-score.
- No authentication. This is a local tool.
- No database. All state is in memory. Restarting the server triggers a fresh score.

---

## 6. Error Handling

| Scenario | Behavior |
|---|---|
| Interests file not found | Print error with example JSON structure, exit 1 |
| Interests file empty or invalid JSON | Print specific parse error, exit 1 |
| Interest item missing `title` field | Print warning for that item, skip it, continue |
| Algolia API timeout (10s) | Print error suggesting retry or checking connection, exit 1 |
| Algolia API non-200 response | Print status code and body, exit 1 |
| Algolia returns empty hits | Print "No stories found for feed: {feed}", exit 0 |
| Model download fails | Let sentence-transformers error propagate (it has clear messages) |
| Cache file corrupted | Log warning, delete cache, recompute all |
| HTML output path not writable | Print error, exit 1 |

---

## 7. Testing Notes

Unit tests should cover:

- **`test_sources.py`**: Mock the Algolia HTTP response and verify `HNStory` mapping. Test null URL handling (self-posts). Test error cases (timeout, bad status).
- **`test_scorers.py`**: Test TF-IDF scorer with known inputs and verify relative ordering (a title about "Rust memory safety" should score higher against an interest about "Rust borrow checker" than an interest about "cooking recipes"). Same for embedding scorer. Test empty inputs.
- **`test_cache.py`**: Test cache save/load roundtrip. Test stale/new detection. Test model mismatch invalidation. Test corrupted cache file handling.
- **`test_output.py`**: Test terminal renderer doesn't crash with empty results. Test HTML output is valid HTML and contains expected elements. Test sorting orders.

Use `pytest`. Mock external calls (Algolia API, sentence-transformers model loading) in tests for speed.

---

## 8. Sample Run

```bash
# First run (downloads model, computes all embeddings)
$ python newsloupe.py -f interests.json
Fetching HN front_page...
Loading model all-MiniLM-L6-v2...
Computing embeddings for 47 interests...
Scoring 30 stories...

HN Front Page — Scored Against Your Interests (2026-03-16)

 #  Title                                          TF-IDF  Embed    Δ      HN Link
 1  Show HN: A Rust-based SQLite replacement         0.82    0.89  +0.07   https://news.ycom...
 2  PostgreSQL 18 released                           0.74    0.85  +0.11   https://news.ycom...
 3  Why we moved off Kubernetes                      0.41    0.78  +0.37   https://news.ycom...
 ...
30  The mass extinction no one is talking about      0.05    0.12  +0.07   https://news.ycom...

Done in 3.8s

# Subsequent run (cached embeddings, only new interests computed)
$ python newsloupe.py --top 5 --html report.html
Fetching HN front_page...
Scoring 30 stories...

 #  Title                                          TF-IDF  Embed    Δ      HN Link
 1  Show HN: A Rust-based SQLite replacement         0.82    0.89  +0.07   https://news.ycom...
 ...
 5  The future of WebAssembly                        0.55    0.61  +0.06   https://news.ycom...

HTML report written to report.html
Done in 1.4s
```

---

## 9. Future Enhancements (not in scope for v1)

These are documented for context but should NOT be implemented now:

- SQLite migration for interests + embeddings + score history
- Domain-based scoring (boost articles from domains you read often)
- LLM-based scoring via Claude/GPT for "vibe matching"
- Negative examples (articles you saw but didn't click)
- Recency decay on interests
- HN metadata signals (points/comments as quality filter)
- Cron + email/Slack digest
- Additional HN sources (Firebase API, scraping, hnrss.org) — see "HN Data Source Options" doc
- Feedback loop (track which recommendations you clicked)

---

## 10. Reference Documents

- **HN Recommender Planning Doc** — higher-level design decisions and rationale
- **HN Data Source Options** — detailed comparison of Algolia, Firebase, hnrss.org, scraping, and built-in RSS for future source implementations
