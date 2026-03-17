#!/usr/bin/env python3
"""Seed the click database from interests.json"""
import argparse
import sys
from click_store import ClickStore


def main():
    parser = argparse.ArgumentParser(
        description="Seed click database from interests.json"
    )
    parser.add_argument(
        "-f", "--file",
        default="interests.json",
        help="Path to interests JSON file (default: interests.json)"
    )
    parser.add_argument(
        "-d", "--database",
        default="clicks.db",
        help="Path to SQLite database (default: clicks.db)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Seed even if database already has clicks"
    )
    args = parser.parse_args()

    store = ClickStore(db_path=args.database)
    existing_count = store.get_click_count()

    if existing_count > 0 and not args.force:
        print(
            f"Database already has {existing_count} clicks. "
            "Use --force to seed anyway.",
            file=sys.stderr
        )
        return 1

    try:
        count = store.seed_from_interests(args.file)
        print(f"✓ Seeded {count} interests from {args.file}")
        print(f"Total clicks in database: {store.get_click_count()}")
        return 0
    except Exception as e:
        print(f"Error seeding database: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
