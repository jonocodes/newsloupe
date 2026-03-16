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
}


@app.on_event("startup")
async def startup():
    state["results"] = await asyncio.to_thread(
        core.run_scoring, state["interests_path"], state["feed"], state["source"], False
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
        core.run_scoring, state["interests_path"], state["feed"], state["source"], False
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
            "read": r.max_score >= state["read_threshold"],
        })
    return JSONResponse({"threshold": state["read_threshold"], "stories": output})


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
