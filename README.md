# newsloupe

Score Hacker News front page articles against your personal reading history. Uses TF-IDF and sentence embeddings side by side to surface what's worth reading.

Results are shown in HN's original ranking order. Each article gets a ✓/✗ based on whether its score falls in the top 25% of today's run — the threshold auto-calibrates each time so you always get a useful signal regardless of absolute score values.

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
python serve.py
# open http://127.0.0.1:8000
```

## Server options

```bash
python serve.py --source scraper   # scrape news.ycombinator.com directly (default)
python serve.py --source algolia   # use Algolia HN Search API
python serve.py --feed show_hn     # score Show HN instead of front page
python serve.py --port 9000
python serve.py --file ~/my-interests.json
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
