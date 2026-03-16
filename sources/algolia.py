import requests
from .base import HNSource, HNStory


class AlgoliaSource(HNSource):
    BASE_URL = "https://hn.algolia.com/api/v1/search"

    def __init__(self, feed: str = "front_page"):
        self.feed = feed

    def fetch_stories(self, count: int = 30) -> list[HNStory]:
        url = f"{self.BASE_URL}?tags={self.feed}&hitsPerPage={count}"
        try:
            response = requests.get(url, timeout=10)
        except requests.Timeout:
            raise RuntimeError(
                "Algolia API timed out after 10s. Check your connection and try again."
            )

        if response.status_code != 200:
            raise RuntimeError(
                f"Algolia API returned {response.status_code}: {response.text}"
            )

        data = response.json()
        hits = data.get("hits", [])
        stories = []
        for hit in hits:
            object_id = hit.get("objectID", "")
            hn_url = f"https://news.ycombinator.com/item?id={object_id}"
            url_val = hit.get("url") or hn_url
            stories.append(HNStory(
                title=hit.get("title", ""),
                url=url_val,
                hn_url=hn_url,
                object_id=object_id,
                points=hit.get("points", 0) or 0,
                num_comments=hit.get("num_comments", 0) or 0,
                author=hit.get("author", "") or "",
                created_at=hit.get("created_at", "") or "",
            ))
        return stories
