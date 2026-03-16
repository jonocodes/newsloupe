import pytest
from unittest.mock import patch, MagicMock
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sources.algolia import AlgoliaSource
from sources.base import HNStory


SAMPLE_HIT = {
    "title": "Show HN: A Rust-based SQLite replacement",
    "url": "https://example.com/rust-sqlite",
    "objectID": "12345",
    "points": 150,
    "num_comments": 42,
    "author": "jsmith",
    "created_at": "2026-01-01T00:00:00Z",
}

SELF_POST_HIT = {
    "title": "Ask HN: Best books for systems programming?",
    "url": None,
    "objectID": "99999",
    "points": 80,
    "num_comments": 20,
    "author": "alice",
    "created_at": "2026-01-02T00:00:00Z",
}


def make_response(hits):
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"hits": hits}
    return mock


def test_fetch_stories_maps_fields():
    with patch("sources.algolia.requests.get", return_value=make_response([SAMPLE_HIT])):
        source = AlgoliaSource()
        stories = source.fetch_stories()

    assert len(stories) == 1
    s = stories[0]
    assert isinstance(s, HNStory)
    assert s.title == SAMPLE_HIT["title"]
    assert s.url == SAMPLE_HIT["url"]
    assert s.hn_url == "https://news.ycombinator.com/item?id=12345"
    assert s.object_id == "12345"
    assert s.points == 150
    assert s.num_comments == 42
    assert s.author == "jsmith"


def test_self_post_url_fallback():
    with patch("sources.algolia.requests.get", return_value=make_response([SELF_POST_HIT])):
        source = AlgoliaSource()
        stories = source.fetch_stories()

    assert stories[0].url == "https://news.ycombinator.com/item?id=99999"


def test_empty_hits():
    with patch("sources.algolia.requests.get", return_value=make_response([])):
        source = AlgoliaSource()
        stories = source.fetch_stories()
    assert stories == []


def test_non_200_raises():
    mock = MagicMock()
    mock.status_code = 503
    mock.text = "Service Unavailable"
    with patch("sources.algolia.requests.get", return_value=mock):
        source = AlgoliaSource()
        with pytest.raises(RuntimeError, match="503"):
            source.fetch_stories()


def test_timeout_raises():
    import requests as req
    with patch("sources.algolia.requests.get", side_effect=req.Timeout()):
        source = AlgoliaSource()
        with pytest.raises(RuntimeError, match="timed out"):
            source.fetch_stories()
