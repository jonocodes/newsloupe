import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pytest
from unittest.mock import patch, MagicMock
from scorers.tfidf import TfidfScorer


def test_tfidf_related_scores_higher():
    interests = ["Rust memory safety borrow checker", "cooking recipes pasta"]
    stories = ["Memory safety in systems languages", "Best Italian pasta dishes"]
    scorer = TfidfScorer()
    scores = scorer.score(interests, stories)
    assert scores[0] > scores[1], "Rust/memory story should score higher against Rust interest"


def test_tfidf_empty_interests():
    scorer = TfidfScorer()
    scores = scorer.score([], ["Some story title"])
    assert scores == [0.0]


def test_tfidf_empty_stories():
    scorer = TfidfScorer()
    scores = scorer.score(["Rust memory safety"], [])
    assert scores == []


def test_tfidf_scores_in_range():
    interests = ["distributed systems", "machine learning", "databases"]
    stories = ["Scaling distributed databases", "A beginner's guide to cooking"]
    scorer = TfidfScorer()
    scores = scorer.score(interests, stories)
    for score in scores:
        assert 0.0 <= score <= 1.0


def test_tfidf_returns_one_per_story():
    interests = ["Rust", "Python"]
    stories = ["Story A", "Story B", "Story C"]
    scorer = TfidfScorer()
    scores = scorer.score(interests, stories)
    assert len(scores) == 3


def test_embedding_scorer_score():
    from scorers.embeddings import EmbeddingScorer
    mock_model = MagicMock()

    def fake_encode(texts, show_progress_bar=False):
        # Return deterministic fake embeddings
        import numpy as np
        np.random.seed(42)
        return np.random.rand(len(texts), 384).astype(np.float32)

    mock_model.encode.side_effect = fake_encode

    with patch("scorers.embeddings.SentenceTransformer", return_value=mock_model):
        scorer = EmbeddingScorer()
        interest_embs = scorer.encode(["Rust memory safety", "Python async"])
        scores = scorer.score(interest_embs, ["Systems programming in Rust", "Pasta recipes"])

    assert len(scores) == 2
    for s in scores:
        assert 0.0 <= s <= 1.0


def test_embedding_scorer_empty_stories():
    from scorers.embeddings import EmbeddingScorer
    mock_model = MagicMock()
    mock_model.encode.return_value = np.zeros((2, 384))

    with patch("scorers.embeddings.SentenceTransformer", return_value=mock_model):
        scorer = EmbeddingScorer()
        interest_embs = np.zeros((2, 384))
        scores = scorer.score(interest_embs, [])

    assert scores == []
