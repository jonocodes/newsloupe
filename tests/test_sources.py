import pytest
from unittest.mock import patch, MagicMock
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sources.algolia import AlgoliaSource
from sources.scraper import ScraperSource
from sources.base import HNStory


# ── Algolia ────────────────────────────────────────────────────────────────────

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


def make_algolia_response(hits):
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"hits": hits}
    return mock


def test_algolia_maps_fields():
    with patch("sources.algolia.requests.get", return_value=make_algolia_response([SAMPLE_HIT])):
        stories = AlgoliaSource().fetch_stories()
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


def test_algolia_self_post_url_fallback():
    with patch("sources.algolia.requests.get", return_value=make_algolia_response([SELF_POST_HIT])):
        stories = AlgoliaSource().fetch_stories()
    assert stories[0].url == "https://news.ycombinator.com/item?id=99999"


def test_algolia_empty_hits():
    with patch("sources.algolia.requests.get", return_value=make_algolia_response([])):
        assert AlgoliaSource().fetch_stories() == []


def test_algolia_non_200_raises():
    mock = MagicMock()
    mock.status_code = 503
    mock.text = "Service Unavailable"
    with patch("sources.algolia.requests.get", return_value=mock):
        with pytest.raises(RuntimeError, match="503"):
            AlgoliaSource().fetch_stories()


def test_algolia_timeout_raises():
    import requests as req
    with patch("sources.algolia.requests.get", side_effect=req.Timeout()):
        with pytest.raises(RuntimeError, match="timed out"):
            AlgoliaSource().fetch_stories()


# ── Scraper ────────────────────────────────────────────────────────────────────

SAMPLE_HTML = """
<html><body><table>
  <tr class="athing" id="42001">
    <td class="titleline"><a href="https://example.com/story">A great article</a></td>
  </tr>
  <tr>
    <td class="subtext">
      <span class="score">120 points</span>
      <a class="hnuser">bob</a>
      <span class="age" title="2026-03-16T10:00:00">3 hours ago</span>
      <a href="item?id=42001">15 comments</a>
    </td>
  </tr>
</table></body></html>
"""

SELF_POST_HTML = """
<html><body><table>
  <tr class="athing" id="42002">
    <td class="titleline"><a href="item?id=42002">Ask HN: What is your stack?</a></td>
  </tr>
  <tr><td class="subtext"></td></tr>
</table></body></html>
"""


def make_scraper_response(html, status=200):
    mock = MagicMock()
    mock.status_code = status
    mock.text = html
    return mock


def test_scraper_maps_fields():
    with patch("sources.scraper.requests.get", return_value=make_scraper_response(SAMPLE_HTML)):
        stories = ScraperSource().fetch_stories()
    assert len(stories) == 1
    s = stories[0]
    assert isinstance(s, HNStory)
    assert s.title == "A great article"
    assert s.url == "https://example.com/story"
    assert s.hn_url == "https://news.ycombinator.com/item?id=42001"
    assert s.object_id == "42001"
    assert s.points == 120
    assert s.num_comments == 15
    assert s.author == "bob"


def test_scraper_self_post_url():
    with patch("sources.scraper.requests.get", return_value=make_scraper_response(SELF_POST_HTML)):
        stories = ScraperSource().fetch_stories()
    assert stories[0].url == "https://news.ycombinator.com/item?id=42002"


def test_scraper_non_200_raises():
    with patch("sources.scraper.requests.get", return_value=make_scraper_response("", status=503)):
        with pytest.raises(RuntimeError, match="503"):
            ScraperSource().fetch_stories()


def test_scraper_timeout_raises():
    import requests as req
    with patch("sources.scraper.requests.get", side_effect=req.Timeout()):
        with pytest.raises(RuntimeError, match="timed out"):
            ScraperSource().fetch_stories()


def test_scraper_empty_page():
    with patch("sources.scraper.requests.get", return_value=make_scraper_response("<html></html>")):
        assert ScraperSource().fetch_stories() == []
