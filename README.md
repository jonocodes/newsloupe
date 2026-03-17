# newsloupe

A personalized wrapper for Hacker News that learns what you like to read.

**How it works:** Browse HN articles as usual. When you click on stories, newsloupe tracks your choices and uses machine learning to predict what you'll find interesting. The more you use it, the better it gets at highlighting articles you'll actually want to read.

**Scoring methods:**
- **TF-IDF** — keyword overlap with your interests
- **Embeddings** — semantic similarity (catches meaning even when words differ)
- **ML predictions** — personalized click probability based on your history (requires 20+ clicks)

Results are shown in HN's original ranking order. Each article gets a ✓/✗ based on whether its score falls in the top 25% of today's batch — the threshold auto-calibrates each run so you always get a useful signal.

## Running with Docker

```bash
docker compose up --build
# open http://localhost:8000
```

`interests.json` is mounted from the host — edit it and hit Re-score without rebuilding.

**Data persistence:** Click history (`clicks.db`) and embeddings cache are stored in a Docker volume named `app_data`. Your click data persists across container restarts.

**Seeding the database in Docker:**
```bash
# Run the seed command inside the running container
docker compose exec newsloupe python seed.py --file interests.json --database /app/data/clicks.db

# Or seed before first run by starting a temporary container
docker compose run --rm newsloupe python seed.py --file interests.json --database /app/data/clicks.db
```

## Running locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Production
uvicorn serve:app --host 127.0.0.1 --port 8000

# Development (with auto-reload)
uvicorn serve:app --host 0.0.0.0 --port 8000 --reload

# open http://127.0.0.1:8000
```

## Configuration

Configure via environment variables:

```bash
# Interests file
export INTERESTS_PATH=/path/to/interests.json

# HN feed: front_page (default), show_hn, ask_hn, story
export HN_FEED=show_hn

# Data source: scraper (default), algolia
export HN_SOURCE=scraper

# Database paths
export CLICKS_DB_PATH=/path/to/clicks.db
export EMBEDDINGS_CACHE_PATH=/path/to/.embeddings_cache.json

# Then run
uvicorn serve:app --host 0.0.0.0 --port 8000 --reload
```

## Your interests

Edit `interests.json` — a JSON array of articles you've found interesting anywhere on the web:

```json
[
  {"title": "How Rust handles memory safety without a GC", "url": "https://example.com"},
  {"title": "Lessons from scaling Postgres to 1TB+", "url": "https://example.com"}
]
```

The `title` field drives scoring. Add 20–30+ entries for meaningful results. Hit Re-score on the page to apply changes without restarting.

## How it works

| Column | What it means |
|---|---|
| **TF-IDF** | Keyword overlap between the article title and your interests. Fast and literal — misses synonyms. |
| **Embed** | Semantic similarity via `all-MiniLM-L6-v2`. Catches meaning even when words differ. |
| **Δ** | Embed minus TF-IDF. Large positive = embeddings found a match the keywords missed. |
| **ML** | Personalized click prediction (0-1 probability) trained on your history. Adapts to what you actually read. |
| **Read** | ✓ if the article scores in the top 25% of today's batch (auto-calibrated per run). |

Interest embeddings are cached in `.embeddings_cache.json` and only recomputed when titles change. The model (~80MB) downloads automatically on first run.

## Click tracking and ML predictions

newsloupe learns from what you actually click. When you click article links, the system records your behavior and trains a personalized machine learning model to predict what you'll want to read next.

**Getting started with ML scoring:**

1. Seed the database from your existing interests (optional but recommended):
   ```bash
   python seed.py --file interests.json
   ```

2. Start using newsloupe normally — clicks are tracked automatically

3. Once you have 20+ clicks, the ML model trains automatically and shows predictions in the **ML** column

The ML scorer uses logistic regression on features like TF-IDF score, embedding score, HN points/comments, and time of day. It shows a probability (0-1) of whether you'll click an article.

**Click data is stored in `clicks.db`** — a local SQLite database. To view your click history, use the API:
```bash
curl http://localhost:8000/api/clicks
```

## Sources

| Source | How it works |
|---|---|
| `scraper` (default) | Scrapes `news.ycombinator.com` directly — always shows exactly what's on the page right now. |
| `algolia` | Queries the Algolia HN Search API — structured JSON but may lag the live front page by some minutes. |

## Running tests

```bash
python -m pytest tests/
```
