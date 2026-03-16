import sys, os, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from cache import EmbeddingCache


def make_cache_file(path, model, embeddings):
    with open(path, "w") as f:
        json.dump({"model": model, "embeddings": embeddings}, f)


def test_roundtrip(tmp_path):
    cache_path = str(tmp_path / "cache.json")
    cache = EmbeddingCache(cache_path=cache_path)
    embeddings = {"title A": [0.1, 0.2], "title B": [0.3, 0.4]}
    cache.save(embeddings)
    loaded = cache.load()
    assert loaded == embeddings


def test_model_mismatch_invalidates(tmp_path):
    cache_path = str(tmp_path / "cache.json")
    make_cache_file(cache_path, "old-model", {"title": [0.1]})
    cache = EmbeddingCache(cache_path=cache_path, model_name="new-model")
    result = cache.load()
    assert result == {}


def test_missing_file_returns_empty(tmp_path):
    cache = EmbeddingCache(cache_path=str(tmp_path / "nonexistent.json"))
    assert cache.load() == {}


def test_corrupted_file_returns_empty(tmp_path):
    cache_path = str(tmp_path / "bad.json")
    with open(cache_path, "w") as f:
        f.write("not json {{{{")
    cache = EmbeddingCache(cache_path=cache_path)
    result = cache.load()
    assert result == {}


def test_stale_and_new():
    cache = EmbeddingCache()
    cached = {"A": [1.0], "B": [2.0], "C": [3.0]}
    current = ["B", "C", "D"]
    stale, new = cache.get_stale_and_new(cached, current)
    assert stale == ["A"]
    assert new == ["D"]


def test_no_stale_no_new():
    cache = EmbeddingCache()
    cached = {"A": [1.0], "B": [2.0]}
    stale, new = cache.get_stale_and_new(cached, ["A", "B"])
    assert stale == []
    assert new == []


def test_all_new():
    cache = EmbeddingCache()
    stale, new = cache.get_stale_and_new({}, ["X", "Y"])
    assert stale == []
    assert set(new) == {"X", "Y"}
