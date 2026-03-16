from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class HNStory:
    title: str
    url: str
    hn_url: str
    object_id: str
    points: int
    num_comments: int
    author: str
    created_at: str


class HNSource(ABC):
    @abstractmethod
    def fetch_stories(self, count: int = 30) -> list[HNStory]:
        """Fetch stories from HN. Returns normalized HNStory list."""
        pass
