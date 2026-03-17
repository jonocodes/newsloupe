#!/usr/bin/env python3
import asyncio
import os
import sys
from datetime import datetime

import numpy as np
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

import core
from output.html import render_html_string
from click_store import ClickStore


# Configuration from environment variables
INTERESTS_PATH = os.environ.get("INTERESTS_PATH", "interests.json")
HN_FEED = os.environ.get("HN_FEED", "front_page")  # front_page, show_hn, ask_hn, story
HN_SOURCE = os.environ.get("HN_SOURCE", "scraper")  # scraper or algolia
CLICKS_DB_PATH = os.environ.get("CLICKS_DB_PATH", "clicks.db")
EMBEDDINGS_CACHE_PATH = os.environ.get("EMBEDDINGS_CACHE_PATH", ".embeddings_cache.json")


def compute_threshold(results) -> float:
    if not results:
        return 0.3
    scores = [r.max_score for r in results]
    return float(np.percentile(scores, 75))


app = FastAPI()

state = {
    "results": [],
    "last_updated": None,
    "read_threshold": 0.3,
    "click_store": None,
}


@app.on_event("startup")
async def startup():
    print(f"Starting newsloupe with config:", file=sys.stderr)
    print(f"  Interests: {INTERESTS_PATH}", file=sys.stderr)
    print(f"  Feed: {HN_FEED}", file=sys.stderr)
    print(f"  Source: {HN_SOURCE}", file=sys.stderr)
    print(f"  Clicks DB: {CLICKS_DB_PATH}", file=sys.stderr)

    state["click_store"] = ClickStore(db_path=CLICKS_DB_PATH)
    state["results"] = await asyncio.to_thread(
        core.run_scoring, INTERESTS_PATH, HN_FEED, HN_SOURCE, False,
        enable_ml=True, click_db_path=CLICKS_DB_PATH
    )
    state["last_updated"] = datetime.now()
    state["read_threshold"] = compute_threshold(state["results"])


@app.get("/", response_class=HTMLResponse)
async def index():
    html = render_html_string(
        state["results"],
        sort_by="hn",
        last_updated=state["last_updated"],
        include_rescore_button=True,
        read_threshold=state["read_threshold"],
        source=HN_SOURCE,
    )
    return HTMLResponse(content=html)


@app.post("/rescore")
async def rescore():
    state["results"] = await asyncio.to_thread(
        core.run_scoring, INTERESTS_PATH, HN_FEED, HN_SOURCE, False,
        enable_ml=True, click_db_path=CLICKS_DB_PATH
    )
    state["last_updated"] = datetime.now()
    state["read_threshold"] = compute_threshold(state["results"])
    return JSONResponse({
        "status": "ok",
        "last_updated": state["last_updated"].isoformat(),
        "story_count": len(state["results"]),
    })


@app.get("/api/results")
async def api_results():
    output = []
    for r in state["results"]:
        output.append({
            "title": r.story.title,
            "url": r.story.url,
            "hn_url": r.story.hn_url,
            "object_id": r.story.object_id,
            "points": r.story.points,
            "num_comments": r.story.num_comments,
            "author": r.story.author,
            "created_at": r.story.created_at,
            "tfidf_score": r.tfidf_score,
            "embedding_score": r.embedding_score,
            "delta": r.delta,
            "max_score": r.max_score,
            "ml_score": r.ml_score,
            "read": r.max_score >= state["read_threshold"],
        })
    return JSONResponse({"threshold": state["read_threshold"], "stories": output})


@app.post("/api/click")
async def track_click(data: dict):
    """Record a click event when user clicks an article link."""
    store = state["click_store"]
    if not store:
        return JSONResponse({"status": "error", "message": "Click store not initialized"}, status_code=500)

    # Find the corresponding story in current results
    object_id = data.get("object_id")
    if not object_id:
        return JSONResponse({"status": "error", "message": "object_id required"}, status_code=400)

    # Find story data
    story_data = None
    for r in state["results"]:
        if r.story.object_id == object_id:
            story_data = r
            break

    if not story_data:
        return JSONResponse({"status": "error", "message": "Story not found"}, status_code=404)

    # Log the click
    import sys
    print(f"Click tracked: {story_data.story.title}", file=sys.stderr)

    # Record click with full metadata
    await asyncio.to_thread(
        store.record_click,
        title=story_data.story.title,
        url=story_data.story.url,
        object_id=story_data.story.object_id,
        hn_url=story_data.story.hn_url,
        tfidf_score=story_data.tfidf_score,
        embedding_score=story_data.embedding_score,
        delta=story_data.delta,
        hn_points=story_data.story.points,
        hn_comments=story_data.story.num_comments,
        author=story_data.story.author,
        created_at=story_data.story.created_at,
    )

    return JSONResponse({"status": "ok", "total_clicks": store.get_click_count()})


@app.get("/api/clicks")
async def get_clicks(limit: int = 100):
    """Get recent click history."""
    store = state["click_store"]
    if not store:
        return JSONResponse({"status": "error", "message": "Click store not initialized"}, status_code=500)

    clicks = await asyncio.to_thread(store.get_all_clicks, limit)
    return JSONResponse({
        "total": store.get_click_count(),
        "clicks": clicks
    })


@app.get("/debug")
async def debug():
    """Debug endpoint showing system state and database info."""
    store = state["click_store"]

    # Get click statistics
    total_clicks = store.get_click_count() if store else 0
    recent_clicks = await asyncio.to_thread(store.get_all_clicks, 10) if store else []

    # Calculate score distributions
    score_stats = {}
    if state["results"]:
        tfidf_scores = [r.tfidf_score for r in state["results"]]
        embed_scores = [r.embedding_score for r in state["results"]]
        ml_scores = [r.ml_score for r in state["results"] if r.ml_score is not None]

        score_stats = {
            "tfidf": {
                "min": float(min(tfidf_scores)),
                "max": float(max(tfidf_scores)),
                "mean": float(np.mean(tfidf_scores)),
            },
            "embedding": {
                "min": float(min(embed_scores)),
                "max": float(max(embed_scores)),
                "mean": float(np.mean(embed_scores)),
            },
            "ml": {
                "count": len(ml_scores),
                "min": float(min(ml_scores)) if ml_scores else None,
                "max": float(max(ml_scores)) if ml_scores else None,
                "mean": float(np.mean(ml_scores)) if ml_scores else None,
            },
        }

    # Analyze click types
    seeded_count = 0
    real_click_count = 0
    top_clicks = []

    if recent_clicks:
        for click in recent_clicks:
            # Seeded clicks have no object_id and synthetic scores (0.7)
            is_seeded = (
                not click.get("object_id") and
                click.get("tfidf_score") == 0.7 and
                click.get("embedding_score") == 0.7
            )
            if is_seeded:
                seeded_count += 1
            else:
                real_click_count += 1

        # Show top 10 for debug
        for click in recent_clicks[:10]:
            is_seeded = (
                not click.get("object_id") and
                click.get("tfidf_score") == 0.7 and
                click.get("embedding_score") == 0.7
            )
            top_clicks.append({
                "title": click.get("title", "")[:80],
                "clicked_at": click.get("clicked_at"),
                "tfidf": click.get("tfidf_score"),
                "embed": click.get("embedding_score"),
                "ml": click.get("ml_score"),
                "type": "seeded" if is_seeded else "real",
                "hn_points": click.get("hn_points"),
            })

    return JSONResponse({
        "config": {
            "interests_path": INTERESTS_PATH,
            "hn_feed": HN_FEED,
            "hn_source": HN_SOURCE,
            "clicks_db_path": CLICKS_DB_PATH,
            "embeddings_cache_path": EMBEDDINGS_CACHE_PATH,
        },
        "state": {
            "stories_loaded": len(state["results"]),
            "last_updated": state["last_updated"].isoformat() if state["last_updated"] else None,
            "read_threshold": state["read_threshold"],
        },
        "clicks": {
            "total": total_clicks,
            "seeded": seeded_count,
            "real": real_click_count,
            "recent_count": len(recent_clicks),
            "top_10": top_clicks,
        },
        "scores": score_stats,
        "ml_enabled": any(r.ml_score is not None for r in state["results"]) if state["results"] else False,
    })


# Run with: uvicorn serve:app --host 0.0.0.0 --port 8000 --reload
# Or use environment variables to configure:
#   INTERESTS_PATH=/path/to/interests.json
#   HN_FEED=show_hn
#   HN_SOURCE=algolia
#   CLICKS_DB_PATH=/path/to/clicks.db
