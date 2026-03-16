#!/usr/bin/env python3
import argparse
import json
import sys
import time

from core import run_scoring
from output.terminal import render_terminal
from output.html import render_html


def parse_args():
    parser = argparse.ArgumentParser(
        description="Score HN front page articles against your interests."
    )
    parser.add_argument("-f", "--file", default="interests.json",
                        help="Path to interests JSON file (default: interests.json)")
    parser.add_argument("-n", "--top", type=int, default=None,
                        help="Show only top N results")
    parser.add_argument("-s", "--sort-by", default="hn", choices=["hn", "tfidf", "embed", "max"],
                        help="Sort by: hn (default, preserves HN order), tfidf, embed, or max")
    parser.add_argument("-t", "--threshold", type=float, default=0.0,
                        help="Only show articles scoring above this threshold")
    parser.add_argument("--html", nargs="?", const="output.html", default=None,
                        metavar="PATH",
                        help="Generate HTML report (default path: output.html)")
    parser.add_argument("--json", action="store_true",
                        help="Output raw JSON to stdout")
    parser.add_argument("--no-cache", action="store_true",
                        help="Force recompute of all embeddings")
    parser.add_argument("--source", default="algolia", choices=["algolia", "scraper"],
                        help="HN data source: algolia or scraper (default: algolia)")
    parser.add_argument("--feed", default="front_page",
                        choices=["front_page", "show_hn", "ask_hn", "story"],
                        help="Feed type (default: front_page)")
    parser.add_argument("--read-threshold", type=float, default=0.3,
                        help="Min score to mark an article as 'read' (default: 0.3)")
    return parser.parse_args()


def main():
    args = parse_args()
    start = time.time()

    try:
        results = run_scoring(
            interests_path=args.file,
            feed=args.feed,
            source=args.source,
            no_cache=args.no_cache,
        )
    except (ValueError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not results:
        sys.exit(0)

    # Filter by threshold
    if args.threshold > 0.0:
        results = [r for r in results if r.max_score >= args.threshold]

    # Sort
    if args.sort_by != "hn":
        sort_key = {
            "tfidf": lambda r: r.tfidf_score,
            "embed": lambda r: r.embedding_score,
            "max": lambda r: r.max_score,
        }[args.sort_by]
        results = sorted(results, key=sort_key, reverse=True)

    # Limit
    if args.top is not None:
        results = results[:args.top]

    # Output
    if args.json:
        output = []
        for r in results:
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
                "read": r.max_score >= args.read_threshold,
            })
        print(json.dumps(output, indent=2))
    else:
        if args.html:
            render_html(results, output_path=args.html, sort_by=args.sort_by,
                        read_threshold=args.read_threshold)
        render_terminal(results, sort_by=args.sort_by, read_threshold=args.read_threshold)

    elapsed = time.time() - start
    print(f"Done in {elapsed:.1f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
