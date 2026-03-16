import json
import os
import sys


class EmbeddingCache:
    def __init__(self, cache_path: str = ".embeddings_cache.json", model_name: str = "all-MiniLM-L6-v2"):
        self.cache_path = cache_path
        self.model_name = model_name

    def load(self) -> dict[str, list[float]]:
        if not os.path.exists(self.cache_path):
            return {}
        try:
            with open(self.cache_path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: cache file corrupted ({e}), recomputing all embeddings.", file=sys.stderr)
            try:
                os.remove(self.cache_path)
            except OSError:
                pass
            return {}

        if data.get("model") != self.model_name:
            return {}
        return data.get("embeddings", {})

    def save(self, embeddings: dict[str, list[float]]):
        with open(self.cache_path, "w") as f:
            json.dump({"model": self.model_name, "embeddings": embeddings}, f)

    def get_stale_and_new(
        self, cached: dict[str, list[float]], current_titles: list[str]
    ) -> tuple[list[str], list[str]]:
        current_set = set(current_titles)
        cached_set = set(cached.keys())
        stale = [t for t in cached_set if t not in current_set]
        new = [t for t in current_titles if t not in cached_set]
        return stale, new
