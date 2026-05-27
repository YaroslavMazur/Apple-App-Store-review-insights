"""
End-to-end smoke for M4.

Fetches real App Store reviews via the M2 fetcher, then runs the full NLP
insights pipeline (sentiment → cluster negatives → actionable insights) and
prints a human-readable report.

Usage:
    cd api && uv run python scripts/run_insights.py [APP_ID] [COUNTRY] [--limit N]

Default: Spotify in the US, 50 reviews.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys

from app.models.domain import SentimentClass
from app.services.fetcher import fetch_all_reviews
from app.services.insights import compute_insights_report
from app.services.metrics import compute_metrics


async def main(app_id: int, country: str, limit: int) -> int:
    print(f"\n=== Fetching every available review for app {app_id} ({country}) ===")
    all_reviews = await fetch_all_reviews(app_id=app_id, country=country)
    print(f"Got {len(all_reviews)} total reviews available")
    if limit < len(all_reviews):
        reviews = random.sample(all_reviews, limit)
        print(f"Randomly sampled {len(reviews)} for analysis")
    else:
        reviews = all_reviews

    metrics = compute_metrics(reviews)
    print("\n=== Rating metrics (from collected reviews) ===")
    print(f"Average: {metrics.average_rating:.2f}  Total: {metrics.total_reviews}")
    for bucket in metrics.distribution:
        bar = "█" * bucket.count
        print(f"  {bucket.rating}★  n={bucket.count:>3}  ({bucket.percentage:>5.1f}%)  {bar}")

    print("\n=== Running NLP insights (this loads HF models on first run) ===")
    report = compute_insights_report(reviews)

    print("\n=== Sentiment breakdown ===")
    pretty_labels = {
        SentimentClass.VERY_NEGATIVE: "Very Negative",
        SentimentClass.NEGATIVE: "Negative",
        SentimentClass.NEUTRAL: "Neutral",
        SentimentClass.POSITIVE: "Positive",
        SentimentClass.VERY_POSITIVE: "Very Positive",
    }
    for cls in SentimentClass:
        n = report.sentiment_breakdown.counts[cls]
        p = report.sentiment_breakdown.percentages[cls]
        bar = "█" * n
        print(f"  {pretty_labels[cls]:>14}  n={n:>3}  ({p:>5.1f}%)  {bar}")

    print(f"\n=== Themes ({len(report.themes)}) ===")
    if not report.themes:
        print("  (no themes — too few negative reviews or BERTopic could not cluster)")
    for theme in report.themes:
        print(f"  Theme #{theme.id}: {theme.label}")
        print(f"    keywords: {', '.join(theme.keywords)}")
        print(
            f"    {len(theme.review_ids)} reviews, "
            f"{theme.share_of_negatives:.1f}% of negatives, "
            f"avg {theme.average_rating:.1f}★"
        )

    print(f"\n=== Actionable insights ({len(report.insights)}) ===")
    for i, insight in enumerate(report.insights, 1):
        print(f"  {i}. [{insight.severity.upper()}] {insight.title} (x{insight.evidence_count})")
        print(f"     {insight.suggestion}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app_id", nargs="?", type=int, default=324684580, help="Apple app id")
    parser.add_argument("country", nargs="?", default="us", help="ISO-3166-1 alpha-2 country code")
    parser.add_argument("--limit", type=int, default=50, help="Max reviews to fetch")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.app_id, args.country, args.limit)))
