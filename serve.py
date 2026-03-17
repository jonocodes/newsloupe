#!/usr/bin/env python3
import argparse
import asyncio
from datetime import datetime

import numpy as np
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

import core
from output.html import render_html_string
from click_store import ClickStore


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
    "interests_path": "interests.json",
    "feed": "front_page",
    "source": "scraper",
    "click_store": None,
}


@app.on_event("startup")
async def startup():
    import os
    clicks_db_path = os.environ.get("CLICKS_DB_PATH", "clicks.db")
    state["click_store"] = ClickStore(db_path=clicks_db_path)
    state["click_db_path"] = clicks_db_path
    state["results"] = await asyncio.to_thread(
        core.run_scoring, state["interests_path"], state["feed"], state["source"], False,
        enable_ml=True, click_db_path=clicks_db_path
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
        source=state["source"],
    )
    return HTMLResponse(content=html)


@app.post("/rescore")
async def rescore():
    state["results"] = await asyncio.to_thread(
        core.run_scoring, state["interests_path"], state["feed"], state["source"], False,
        enable_ml=True, click_db_path=state.get("click_db_path", "clicks.db")
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


def parse_args():
    parser = argparse.ArgumentParser(description="Serve newsloupe as a web app.")
    parser.add_argument("-f", "--file", default="interests.json",
                        help="Path to interests JSON file")
    parser.add_argument("--feed", default="front_page",
                        choices=["front_page", "show_hn", "ask_hn", "story"],
                        help="Feed tag")
    parser.add_argument("--source", default="scraper", choices=["algolia", "scraper"],
                        help="HN data source (default: algolia)")
    parser.add_argument("-p", "--port", type=int, default=8000,
                        help="Port to serve on")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Host to bind to")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    state["interests_path"] = args.file
    state["feed"] = args.feed
    state["source"] = args.source
    uvicorn.run(app, host=args.host, port=args.port)
