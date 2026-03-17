import json
import sys
import numpy as np
from dataclasses import dataclass

from sources.base import HNStory
from sources.algolia import AlgoliaSource
from sources.scraper import ScraperSource
from scorers.tfidf import TfidfScorer
from scorers.embeddings import EmbeddingScorer
from scorers.ml import MLScorer
from cache import EmbeddingCache
from click_store import ClickStore


@dataclass
class ScoredStory:
    story: HNStory
    tfidf_score: float
    embedding_score: float
    delta: float
    max_score: float
    ml_score: float = None  # ML prediction score (0-1 probability)


def load_and_validate_interests(path: str) -> list[dict]:
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        raise ValueError(
            f'Interests file not found: {path}\n'
            'Create it with entries like:\n'
            '[{"title": "How Rust handles memory safety", "url": "https://example.com"}]'
        )
    except json.JSONDecodeError as e:
        raise ValueError(f"Interests file is not valid JSON: {e}")

    if not isinstance(data, list) or len(data) == 0:
        raise ValueError("Interests file must be a non-empty JSON array.")

    valid = []
    for i, item in enumerate(data):
        if not isinstance(item, dict) or "title" not in item:
            print(f"Warning: interests[{i}] missing 'title' field, skipping.", file=sys.stderr)
            continue
        valid.append(item)

    if not valid:
        raise ValueError("No valid interest entries found (all were missing 'title').")

    return valid


def run_scoring(
    interests_path: str,
    feed: str,
    source: str,
    no_cache: bool,
    enable_ml: bool = True,
    click_db_path: str = "clicks.db",
) -> list[ScoredStory]:
    interests = load_and_validate_interests(interests_path)
    interest_titles = [i["title"] for i in interests]

    print(f"Fetching HN {feed} via {source}...", file=sys.stderr)
    if source == "scraper":
        hn_source = ScraperSource(feed=feed)
    else:
        hn_source = AlgoliaSource(feed=feed)
    stories = hn_source.fetch_stories(count=30)

    if not stories:
        print(f"No stories found for feed: {feed}", file=sys.stderr)
        return []

    story_titles = [s.title for s in stories]

    print("Scoring with TF-IDF...", file=sys.stderr)
    tfidf_scorer = TfidfScorer()
    tfidf_scores = tfidf_scorer.score(interest_titles, story_titles)

    print("Loading model all-MiniLM-L6-v2...", file=sys.stderr)
    embedding_scorer = EmbeddingScorer()

    if no_cache:
        print(f"Computing embeddings for {len(interest_titles)} interests...", file=sys.stderr)
        interest_vecs = embedding_scorer.encode(interest_titles)
        interest_embeddings = np.array(interest_vecs)
    else:
        import os
        cache_path = os.environ.get("EMBEDDINGS_CACHE_PATH", ".embeddings_cache.json")
        cache = EmbeddingCache(cache_path=cache_path)
        cached_embeddings = cache.load()
        stale, new = cache.get_stale_and_new(cached_embeddings, interest_titles)

        for title in stale:
            del cached_embeddings[title]

        if new:
            print(f"Computing embeddings for {len(new)} interests...", file=sys.stderr)
            new_vecs = embedding_scorer.encode(new)
            for title, vec in zip(new, new_vecs):
                cached_embeddings[title] = vec.tolist()
        else:
            print("Using cached embeddings.", file=sys.stderr)

        cache.save(cached_embeddings)
        interest_embeddings = np.array([cached_embeddings[t] for t in interest_titles])

    print(f"Scoring {len(stories)} stories...", file=sys.stderr)
    embedding_scores = embedding_scorer.score(interest_embeddings, story_titles)

    # Build initial results
    results = []
    for story, tfidf, embed in zip(stories, tfidf_scores, embedding_scores):
        results.append(ScoredStory(
            story=story,
            tfidf_score=tfidf,
            embedding_score=embed,
            delta=embed - tfidf,
            max_score=max(tfidf, embed),
        ))

    # Add ML predictions if enabled
    if enable_ml:
        ml_scorer = MLScorer(min_training_samples=20)
        click_store = ClickStore(db_path=click_db_path)
        training_data = click_store.get_training_data(min_clicks=20)

        if training_data:
            print(f"Training ML model on {len(training_data)} clicks...", file=sys.stderr)
            if ml_scorer.train(training_data):
                ml_predictions = ml_scorer.predict(results)
                if ml_predictions:
                    for result, ml_score in zip(results, ml_predictions):
                        result.ml_score = ml_score
                    print(f"ML predictions generated.", file=sys.stderr)

                    # Print feature importance for debugging
                    importance = ml_scorer.get_feature_importance()
                    if importance:
                        print("ML feature importance:", importance, file=sys.stderr)
        else:
            print("Insufficient click data for ML (<20 clicks). Using semantic scoring only.", file=sys.stderr)

    return results
