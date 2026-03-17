import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from contextlib import contextmanager


class ClickStore:
    def __init__(self, db_path: str = "clicks.db"):
        self.db_path = db_path
        self._ensure_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ensure_schema(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS clicks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    object_id TEXT,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    hn_url TEXT,
                    clicked_at TEXT NOT NULL,
                    tfidf_score REAL,
                    embedding_score REAL,
                    delta REAL,
                    hn_points INTEGER,
                    hn_comments INTEGER,
                    author TEXT,
                    created_at TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_clicked_at ON clicks(clicked_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_object_id ON clicks(object_id)
            """)

    def record_click(
        self,
        title: str,
        url: str,
        object_id: Optional[str] = None,
        hn_url: Optional[str] = None,
        tfidf_score: Optional[float] = None,
        embedding_score: Optional[float] = None,
        delta: Optional[float] = None,
        hn_points: Optional[int] = None,
        hn_comments: Optional[int] = None,
        author: Optional[str] = None,
        created_at: Optional[str] = None,
    ):
        """Record a click event with article metadata and scores."""
        clicked_at = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO clicks (
                    object_id, title, url, hn_url, clicked_at,
                    tfidf_score, embedding_score, delta,
                    hn_points, hn_comments, author, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                object_id, title, url, hn_url, clicked_at,
                tfidf_score, embedding_score, delta,
                hn_points, hn_comments, author, created_at
            ))

    def get_all_clicks(self, limit: Optional[int] = None) -> list[dict]:
        """Retrieve all clicks, optionally limited to most recent N."""
        with self._conn() as conn:
            if limit:
                cursor = conn.execute("""
                    SELECT * FROM clicks ORDER BY clicked_at DESC LIMIT ?
                """, (limit,))
            else:
                cursor = conn.execute("""
                    SELECT * FROM clicks ORDER BY clicked_at DESC
                """)
            return [dict(row) for row in cursor.fetchall()]

    def get_click_count(self) -> int:
        """Get total number of clicks."""
        with self._conn() as conn:
            cursor = conn.execute("SELECT COUNT(*) as count FROM clicks")
            return cursor.fetchone()["count"]

    def get_training_data(self, min_clicks: int = 20) -> Optional[list[dict]]:
        """
        Get click data suitable for training ML model.
        Returns None if insufficient data (< min_clicks).
        """
        count = self.get_click_count()
        if count < min_clicks:
            return None
        return self.get_all_clicks()

    def seed_from_interests(self, interests_path: str):
        """
        Seed the click database from interests.json.
        Each interest is treated as a historical click with estimated scores.
        """
        if not Path(interests_path).exists():
            raise FileNotFoundError(f"Interests file not found: {interests_path}")

        with open(interests_path) as f:
            interests = json.load(f)

        if not isinstance(interests, list):
            raise ValueError("Interests file must be a JSON array")

        count = 0
        for item in interests:
            if not isinstance(item, dict) or "title" not in item:
                continue

            # Use synthetic click time (spread over past 30 days for variety)
            # In reality these are just interests, not actual clicks
            self.record_click(
                title=item["title"],
                url=item.get("url", ""),
                tfidf_score=0.7,  # Synthetic high score (they're interests!)
                embedding_score=0.7,
                delta=0.0,
            )
            count += 1

        return count
