"""
Live smoke test against the real Apple App Store.

Hits Apple's API via `appstorescraperpy` to confirm the M2 fetcher works end-to-end.
Skipped from automated CI; run manually:

    cd api && uv run python scripts/smoke_fetcher.py [APP_ID] [COUNTRY]

Default: Spotify in the US.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter

from app.services.fetcher import fetch_reviews


async def main(app_id: int, country: str, limit: int) -> int:
    print(f"Fetching up to {limit} reviews for app_id={app_id}, country={country!r}…")
    reviews = await fetch_reviews(app_id=app_id, country=country, limit=limit)
    print(f"✓ Got {len(reviews)} reviews\n")

    if not reviews:
        print("✗ No reviews returned.")
        return 1

    counts = Counter(r.rating for r in reviews)
    avg = sum(r.rating for r in reviews) / len(reviews)
    print(f"Average rating: {avg:.2f}")
    print("Distribution:")
    for star in range(1, 6):
        n = counts.get(star, 0)
        bar = "█" * n
        print(f"  {star}★ {n:>3} {bar}")

    print("\nMost recent 3 reviews:")
    for review in reviews[:3]:
        body = review.body.replace("\n", " ")
        if len(body) > 120:
            body = body[:117] + "…"
        print(f"  [{review.rating}★] {review.title!r}  — {review.author}")
        print(f"        {body}")
        print(f"        id={review.id}  date={review.created_at.isoformat()}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app_id", nargs="?", type=int, default=324684580, help="Apple app id")
    parser.add_argument("country", nargs="?", default="us", help="ISO-3166-1 alpha-2 country code")
    parser.add_argument("--limit", type=int, default=50, help="Max reviews to fetch")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.app_id, args.country, args.limit)))
