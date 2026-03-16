# newsloupe

Score Hacker News front page articles against your personal reading history. Uses TF-IDF and sentence embeddings side by side so you can see which method surfaces better recommendations.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
# Score today's HN front page
python newsloupe.py

# Show only top 10, sorted by embedding score
python newsloupe.py --top 10 --sort-by embed

# Only show articles scoring above 0.3
python newsloupe.py --threshold 0.3

# Generate an HTML report
python newsloupe.py --html report.html

# Output raw JSON
python newsloupe.py --json

# Score Show HN instead of front page
python newsloupe.py --feed show_hn

# Force recompute all embeddings (ignore cache)
python newsloupe.py --no-cache
```

## Web server

```bash
python serve.py
# open http://127.0.0.1:8000
```

Serves the scored results as an HTML page with a Re-score button. Options: `--port`, `--host`, `--feed`, `--file`.

## Your interests

Edit `interests.json` — a JSON array of articles you've found interesting anywhere on the web:

```json
[
  {"title": "How Rust handles memory safety without a GC", "url": "https://example.com"},
  {"title": "Lessons from scaling Postgres to 1TB+", "url": "https://example.com"}
]
```

The `title` field drives scoring. Add 20–30+ entries for meaningful results. The file is read fresh each run.

## How it works

| Method | Description |
|---|---|
| **TF-IDF** | Keyword overlap between your interest titles and HN titles. Fast, deterministic, lexical. |
| **Embed** | Semantic similarity via `all-MiniLM-L6-v2` (sentence-transformers). Catches meaning even when words differ. |
| **Δ** | `embed − tfidf`. Large positive delta means the embedding found a match the keywords missed. |

Interest embeddings are cached in `.embeddings_cache.json` and recomputed only when titles change. The first run downloads the model (~80MB).

## CLI flags

| Flag | Default | Description |
|---|---|---|
| `-f`, `--file` | `interests.json` | Path to interests file |
| `-n`, `--top` | all | Show top N results |
| `-s`, `--sort-by` | `max` | Sort by `tfidf`, `embed`, or `max` |
| `-t`, `--threshold` | `0.0` | Hide articles below this score |
| `--html [PATH]` | `output.html` | Write HTML report |
| `--json` | off | Output JSON to stdout |
| `--no-cache` | off | Recompute all embeddings |
| `--feed` | `front_page` | `front_page`, `show_hn`, `ask_hn` |
