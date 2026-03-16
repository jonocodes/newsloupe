import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sources.base import HNStory
from core import ScoredStory
from output.html import render_html_string, render_html


def make_story(title="Test Story", score=0.5):
    story = HNStory(
        title=title,
        url="https://example.com",
        hn_url="https://news.ycombinator.com/item?id=1",
        object_id="1",
        points=100,
        num_comments=10,
        author="user",
        created_at="2026-01-01T00:00:00Z",
    )
    return ScoredStory(
        story=story,
        tfidf_score=score,
        embedding_score=score + 0.05,
        delta=0.05,
        max_score=score + 0.05,
    )


def test_render_html_string_contains_title():
    results = [make_story("Rust memory safety", 0.8)]
    html = render_html_string(results)
    assert "Rust memory safety" in html


def test_render_html_string_is_valid_html():
    results = [make_story("Test", 0.5)]
    html = render_html_string(results)
    assert html.strip().startswith("<!DOCTYPE html>")
    assert "</html>" in html


def test_render_html_string_no_rescore_by_default():
    results = [make_story()]
    html = render_html_string(results, include_rescore_button=False)
    assert '<button id="rescore-btn"' not in html


def test_render_html_string_has_rescore_button():
    results = [make_story()]
    html = render_html_string(results, include_rescore_button=True)
    assert "rescore-btn" in html


def test_render_html_shows_source():
    results = [make_story()]
    html = render_html_string(results, source="scraper")
    assert "scraper" in html


def test_render_html_shows_legend():
    results = [make_story()]
    html = render_html_string(results)
    assert "TF-IDF" in html
    assert "Embed" in html
    assert "legend" in html


def test_render_html_default_hn_order():
    r1 = make_story("First on HN", 0.1)
    r2 = make_story("Second on HN", 0.9)
    html = render_html_string([r1, r2], sort_by="hn")
    assert html.index("First on HN") < html.index("Second on HN")


def test_render_html_sort_by_tfidf():
    r1 = ScoredStory(make_story("High tfidf").story, tfidf_score=0.9, embedding_score=0.5, delta=-0.4, max_score=0.9)
    r2 = ScoredStory(make_story("Low tfidf").story, tfidf_score=0.1, embedding_score=0.9, delta=0.8, max_score=0.9)
    html = render_html_string([r1, r2], sort_by="tfidf")
    assert html.index("High tfidf") < html.index("Low tfidf")


def test_render_html_read_threshold():
    r1 = make_story("High scorer", 0.8)   # max_score=0.85, above threshold
    r2 = make_story("Low scorer", 0.1)    # max_score=0.15, below threshold
    html = render_html_string([r1, r2], read_threshold=0.5)
    high_idx = html.index("High scorer")
    low_idx = html.index("Low scorer")
    high_row = html[high_idx:high_idx + 800]
    low_row = html[low_idx:low_idx + 800]
    assert "✓" in high_row
    assert "✗" in low_row


def test_render_html_file(tmp_path):
    output_file = str(tmp_path / "report.html")
    results = [make_story("Test story", 0.6)]
    render_html(results, output_path=output_file)
    with open(output_file) as f:
        content = f.read()
    assert "Test story" in content
