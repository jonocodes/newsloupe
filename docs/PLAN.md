# newsloupe — Planning Doc

## Goal

Build a Python CLI tool ("newsloupe") that scores Hacker News front page articles against a personal interest profile, using two scoring methods (TF-IDF and sentence embeddings) side by side for evaluation.

---

## System Overview

```
interests.json ──┐
                  ├──▶ scorer.py ──▶ terminal output (ranked table)
HN API (top 30) ─┘
```

The system has two distinct halves:

- **Interest profile** — a manually maintained JSON file of articles you've found interesting from anywhere on the web.
- **Scoring target** — the current HN front page (top 30 stories), fetched live via the HN Firebase API.

The scorer computes relevance scores using both methods and prints a comparison table so you can evaluate which approach surfaces better recommendations.

---

## Interest Profile (`interests.json`)

A flat JSON array of objects:

```json
[
  {"title": "How Rust handles memory safety without a GC", "url": "https://example.com/rust-memory"},
  {"title": "Lessons from scaling Postgres to 1TB+", "url": "https://example.com/pg-scale"},
  {"title": "Why every startup should delay hiring a VP of Sales", "url": "https://example.com/vp-sales"}
]
```

**Fields:**

- `title` (required) — the article title. This is the primary signal for both scoring methods.
- `url` (required) — for your reference and potential future use (e.g., domain-based scoring). Not used in v1 scoring.

**Future considerations:**

- Optional `tags` field for manual topic categorization.
- Optional `rating` (1-5) to weight some articles more heavily.
- Optional `date_added` for recency weighting (your interests may shift over time).
- Migration to SQLite for tracking score history, click feedback, and more flexible querying.

---

## Storage & Caching

**v1 approach:** JSON file for interests, file-based embedding cache.

**Interest storage:** `interests.json` — you maintain this manually. The system reads it each run and detects changes.

**Embedding cache:** `.embeddings_cache.json` — stores a mapping of each interest title to its embedding vector, plus a hash of the full interests file for invalidation. On each run:

1. Load `interests.json` and compute a content hash.
2. Load `.embeddings_cache.json` if it exists.
3. If the cache hash matches, use cached embeddings. Compute embeddings only for any new titles not in the cache.
4. If the hash doesn't match (titles removed or edited), do a targeted recompute: keep cached embeddings for titles that still exist, compute new ones, drop stale ones.
5. Write updated cache back to disk.

This means after the first run, adding a few new articles to your interests only costs ~50ms of embedding time instead of re-embedding the entire corpus.

**TF-IDF is always recomputed** — it's fast enough (<50ms) that caching isn't worth the complexity. The vectorizer needs to see the full corpus (interests + HN titles) together anyway.

**Expected performance:**

| Phase | First run | Subsequent runs |
|---|---|---|
| Model load | ~2s (one-time download: ~80MB) | ~1s |
| Algolia fetch | ~200ms | ~200ms |
| Embed interests | ~1-2s (for ~100 titles) | ~50ms (only new titles) |
| Embed HN titles | ~200ms | ~200ms |
| TF-IDF scoring | <50ms | <50ms |
| Embedding scoring | <50ms | <50ms |
| **Total** | **~4s** | **~1.5s** |

**Future (v2):** Migrate to SQLite. Store interests, embeddings, score history, and optionally click feedback in a single `hn_recommender.db` file. This enables tracking how your interests shift over time and building a feedback loop.

---

## Data Ingestion: Algolia HN Search API

**Endpoint:** `https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=30`

Single HTTP request returns structured JSON with a `hits` array. No auth, no API key.

**What we get per story:**

- `title` — primary scoring input
- `url` — the linked article
- `objectID` — HN item ID (for building discussion link)
- `author` — submitter username
- `points` — HN score
- `num_comments` — comment count
- `created_at` — submission timestamp

**Other available Algolia tag filters:**

- `tags=front_page` — current front page (our default)
- `tags=show_hn` — Show HN posts
- `tags=ask_hn` — Ask HN posts
- `tags=story` — all stories (combined with `search_by_date` for newest)
- Can combine with `numericFilters=points>50` or time windows via `created_at_i`

**Why Algolia:**

- One request, fully structured JSON, rich metadata.
- Supports multiple feed types via tag filters.
- No API key required.

**Known risks:**

- The `hn-search` GitHub repo was archived on Feb 10, 2026. Algolia says the new codebase is in a private repo.
- Occasional data staleness has been reported (index lagging by hours).
- The API still powers `hn.algolia.com` itself, so it's not going away, but maintenance visibility is reduced.

**Mitigation:** All HN data access goes through an abstract `HNSource` interface. Only the Algolia implementation is built for v1, but the interface is designed so that a Firebase API, scraping, or hnrss.org backend could be swapped in without changing the scorer or output code. See the separate "HN Data Source Options" document for details on alternatives.

**Dependencies:** `requests`

---

## Scoring Method 1: TF-IDF + Cosine Similarity

**How it works:**

1. Collect all interest titles into a corpus.
2. For each HN article title, add it to the corpus and fit a TF-IDF vectorizer.
3. Compute cosine similarity between the HN title vector and every interest title vector.
4. The score for that HN article is the **max similarity** to any single interest (i.e., "how close is this to your single most related interest?").

**Pros:**

- No external dependencies beyond scikit-learn.
- Fast, deterministic, runs offline.
- Easy to debug — you can inspect which keywords drove the match.

**Cons:**

- Purely lexical — "Rust borrow checker" won't match "memory safety in systems languages."
- Sensitive to title phrasing and vocabulary.

**Implementation notes:**

- Use `TfidfVectorizer` with default English stop words.
- Consider using both unigrams and bigrams (`ngram_range=(1, 2)`) to catch phrases like "machine learning" or "distributed systems."
- Normalize scores to 0–1 range for clean comparison.

---

## Scoring Method 2: Sentence Embeddings + Cosine Similarity

**How it works:**

1. Load a pre-trained sentence-transformers model.
2. Encode all interest titles into embedding vectors (cache these).
3. Encode each HN article title.
4. Compute cosine similarity between the HN title embedding and every interest embedding.
5. Score = **max similarity** (same as TF-IDF approach).

**Model choice:** `all-MiniLM-L6-v2`

- 80MB, fast inference on CPU.
- Good balance of quality and speed for short text.
- If results feel weak, upgrade to `all-mpnet-base-v2` (420MB, better quality).

**Pros:**

- Captures semantic similarity — "Rust memory model" matches "safe systems programming."
- Handles paraphrasing and synonyms well.
- Still fully local, no API key needed.

**Cons:**

- Slower than TF-IDF (though still fast for 30 articles).
- Harder to explain *why* something scored high.
- First run downloads the model (~80MB).

**Implementation notes:**

- Cache interest embeddings to a `.npy` file alongside a hash of `interests.json`. Recompute only when the file changes.
- Embedding computation for 30 HN titles is ~1 second on CPU, so no batching concerns.

---

## Output

### Terminal (default)

Using the `rich` library for a formatted table. Example output:

```
HN Front Page — Scored Against Your Interests (2026-03-16)

 #  Title                                      TF-IDF  Embed   Δ    HN Link
 1  Show HN: A Rust-based SQLite replacement    0.82    0.89   +0.07  https://news.ycom...
 2  PostgreSQL 18 released                      0.74    0.85   +0.11  https://news.ycom...
 3  Why we moved off Kubernetes                 0.41    0.78   +0.37  https://news.ycom...
 4  The mass extinction no one is talking about  0.05    0.12   +0.07  https://news.ycom...
...
```

**Columns:**

- **#** — rank (sorted by the higher of the two scores, or configurable)
- **Title** — HN article title (truncated to fit)
- **TF-IDF** — score from method 1 (0–1)
- **Embed** — score from method 2 (0–1)
- **Δ** — difference between the two (highlights where they disagree, which is where the interesting evaluation happens)
- **HN Link** — `https://news.ycombinator.com/item?id={id}`

**Sorting:** Default sort by the max of the two scores. Flag to sort by either method individually.

### HTML (via `--html` flag)

When `--html` or `--html output.html` is passed, generates a self-contained single HTML file with no external dependencies (all CSS inline). Features:

- Same data as the terminal table but with clickable title links (to the article) and HN discussion links
- Color-coded scores (green gradient for high relevance, fading to gray for low)
- Column sorting — click any header to re-sort by that column
- Score bar visualization alongside the numbers for quick scanning
- Responsive layout that works on desktop and mobile
- Timestamp in the header showing when the report was generated

The HTML file is written to `output.html` by default (or a custom path). It is not auto-opened — you open it yourself or have a cron job serve/send it.

Both outputs are generated from the same scored data, just rendered differently.

---

## CLI Interface

```
python hn_recommender.py [OPTIONS]

Options:
  -f, --file PATH       Path to interests JSON file (default: interests.json)
  -n, --top N           Show top N results instead of all 30 (default: all)
  -s, --sort-by METHOD  Sort by: "tfidf", "embed", or "max" (default: max)
  -t, --threshold FLOAT Only show articles scoring above this (default: 0.0)
  --html [PATH]         Generate HTML report (default path: output.html)
  --json                Output raw JSON instead of table
  --no-cache            Force recompute of all embeddings
  --source SOURCE       HN source: "algolia" (default: algolia)
  --feed FEED           Algolia feed tag: "front_page", "show_hn", "ask_hn" (default: front_page)
```

---

## Project Structure

```
hn-recommender/
├── hn_recommender.py      # main script / CLI entry point
├── sources/
│   ├── __init__.py
│   ├── base.py            # abstract HNSource interface
│   └── algolia.py         # Algolia implementation
├── scorers/
│   ├── __init__.py
│   ├── tfidf.py           # TF-IDF scorer
│   └── embeddings.py      # sentence-transformers scorer
├── output/
│   ├── __init__.py
│   ├── terminal.py        # rich table output
│   └── html.py            # self-contained HTML report generator
├── cache.py               # embedding cache manager
├── interests.json         # your interest profile (you maintain this)
├── requirements.txt       # requests, scikit-learn, sentence-transformers, rich, numpy
├── .embeddings_cache.json # auto-generated, cached interest embeddings
└── README.md
```

---

## Dependencies

```
requests
scikit-learn
sentence-transformers
rich
numpy
```

All installable via pip. No API keys needed. The sentence-transformers model downloads on first run.

---

## Related Projects & Prior Art

- **[selenium-hacker-news-scraper](https://github.com/alexanderjuxoncobb/selenium-hacker-news-scraper)** — Closest to our project. AI-powered HN digest with local embeddings + selective OpenAI, web dashboard, multi-user email digests, PostgreSQL. Full-stack platform (FastAPI, Railway). Author stopped hosting due to costs. Our project is intentionally lighter and local-first.
- **[hn-recommendation-api](https://github.com/julien040/hn-recommendation-api)** — Embedding-based HN recommendation using Diffbot + OpenAI ada-002 + Faiss HNSW index. Recommends similar HN posts to a *given HN post*, not from external history. Different use case but relevant technique (embeddings + cosine similarity).
- **[Scour](https://scour.ing)** — Personalized content feed where you define interests in your own words and it ranks content by relevance. Conceptually similar but text-described interests rather than article history.
- **[circumflex](https://github.com/bensadeh/circumflex)** — Beautiful terminal HN client (Go) with read history tracking and favorites. No scoring or recommendation, but good UX reference for terminal-based HN tools.
- **[positive_hackernews](https://github.com/garritfra/positive_hackernews)** — RSS feed that uses sentiment analysis to filter HN for positive stories. Simple example of filtering HN output through a scoring function.
- **[NEWSense](https://github.com/akshay-madar/NEWSense-news-recommendation-system-using-twitter)** — Hybrid-filtering news recommendation using Twitter reading history (collaborative + content-based). Academic project, uses TF-IDF + cosine similarity + K-means clustering. Relevant technique reference.

**Gap we fill:** No existing project offers a simple, local-first CLI tool that takes an external reading history (from any source) and scores HN articles against it, with multiple scoring methods for comparison.

---

## Future Enhancements (v2+)

- **Domain-based scoring** — extract domains from interest URLs and boost HN articles from the same domains.
- **LLM-based scoring** — pass your top interests + an HN title to Claude/GPT and ask "would this person find this interesting? why?" for richer, explainable ranking.
- **Cron + email/Slack digest** — run on a schedule and send a morning summary.
- **Negative examples** — track articles you saw but *didn't* click to improve scoring.
- **Recency decay** — weight recent interests more heavily than old ones.
- **HN metadata signals** — factor in HN score and comment count as a quality filter.
- **Web UI / HTML report** — render results as a simple page instead of terminal output.
- **Multiple targets** — score against Lobsters, Reddit, or RSS feeds using the same interest profile.

---

## Open Questions

1. **Aggregation strategy:** Using max similarity (closest single match) vs. mean of top-K matches. Max is more aggressive — a single strong match surfaces the article. Mean-of-top-3 would require broader interest alignment. Worth testing both.
2. **Minimum interest corpus size:** How many articles do you need before scores are meaningful? Probably 20–30 minimum. Below that, TF-IDF will be especially noisy.
3. **Score calibration:** TF-IDF and embedding scores won't be on the same effective scale even though both are 0–1. May need to normalize or use percentile ranks for fair comparison.
