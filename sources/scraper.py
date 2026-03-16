import requests
from bs4 import BeautifulSoup
from .base import HNSource, HNStory

HN_URL = "https://news.ycombinator.com/"

FEED_PATHS = {
    "front_page": "",
    "show_hn": "show",
    "ask_hn": "ask",
    "new": "newest",
}


class ScraperSource(HNSource):
    def __init__(self, feed: str = "front_page"):
        self.feed = feed

    def fetch_stories(self, count: int = 30) -> list[HNStory]:
        path = FEED_PATHS.get(self.feed, "")
        url = HN_URL + path
        try:
            response = requests.get(url, timeout=10, headers={"User-Agent": "newsloupe/1.0"})
        except requests.Timeout:
            raise RuntimeError("HN scrape timed out after 10s. Check your connection.")

        if response.status_code != 200:
            raise RuntimeError(f"HN returned {response.status_code}")

        soup = BeautifulSoup(response.text, "html.parser")
        stories = []

        title_rows = soup.select("tr.athing")
        for row in title_rows[:count]:
            object_id = row.get("id", "")
            hn_url = f"https://news.ycombinator.com/item?id={object_id}"

            title_el = row.select_one(".titleline > a")
            if not title_el:
                continue
            title = title_el.get_text()
            article_url = title_el.get("href", hn_url)
            if article_url.startswith("item?id="):
                article_url = "https://news.ycombinator.com/" + article_url

            # metadata is in the next sibling row (.subtext)
            subrow = row.find_next_sibling("tr")
            points = 0
            num_comments = 0
            author = ""
            created_at = ""
            if subrow:
                score_el = subrow.select_one(".score")
                if score_el:
                    try:
                        points = int(score_el.get_text().split()[0])
                    except (ValueError, IndexError):
                        pass

                author_el = subrow.select_one(".hnuser")
                if author_el:
                    author = author_el.get_text()

                age_el = subrow.select_one(".age")
                if age_el:
                    created_at = age_el.get("title", age_el.get_text())

                # last link in subtext is usually "N comments"
                links = subrow.select("a")
                if links:
                    last_link = links[-1].get_text()
                    if "comment" in last_link:
                        try:
                            num_comments = int(last_link.split()[0])
                        except (ValueError, IndexError):
                            pass

            stories.append(HNStory(
                title=title,
                url=article_url,
                hn_url=hn_url,
                object_id=object_id,
                points=points,
                num_comments=num_comments,
                author=author,
                created_at=created_at,
            ))

        return stories
