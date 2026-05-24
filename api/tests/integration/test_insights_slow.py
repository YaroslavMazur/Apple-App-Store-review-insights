"""
Slow integration test: actually loads the real HuggingFace models from
docs/nlp-analysis.md and exercises the full insights pipeline on a small
fixture. Marked @pytest.mark.slow so it's skipped by default in CI.

Run locally with:

    cd api && uv run pytest -m slow tests/integration/test_insights_slow.py -s
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.models.domain import NEGATIVE_CLASSES, Review, SentimentClass
from app.services import insights as svc

pytestmark = pytest.mark.slow


def _review(rating: int, idx: int, title: str, body: str) -> Review:
    return Review(
        id=f"r{idx}",
        app_id=1,
        country="us",
        title=title,
        body=body,
        rating=rating,
        author=f"user{idx}",
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        is_edited=False,
    )


@pytest.fixture
def labeled_reviews() -> list[Review]:
    """A small hand-curated set: 5 clearly negative, 3 positive, 2 neutral-ish."""
    return [
        # Negative cluster A: crashes / bugs
        _review(
            1, 0, "Constant crashes", "App crashes every time I open it after update. Unusable bug."
        ),
        _review(1, 1, "App freezes", "Freezes on startup and crashes. Broken since last update."),
        _review(2, 2, "Buggy", "So many bugs. Crashes when I try to play music."),
        # Negative cluster B: pricing / ads
        _review(
            2,
            3,
            "Too expensive",
            "Subscription price doubled. Way too expensive now for what you get.",
        ),
        _review(1, 4, "Ads everywhere", "Free tier is unusable, ads every two songs. Greedy."),
        # Positive
        _review(5, 5, "Love it", "Best music app ever. The recommendations are spot on."),
        _review(5, 6, "Amazing", "Discover Weekly is incredible. Found so many new artists."),
        _review(4, 7, "Great", "Pretty good app, search is smooth and offline works well."),
        # Neutral-ish
        _review(3, 8, "Okay", "It does what it says. Nothing special, nothing bad."),
        _review(3, 9, "Decent", "Mixed feelings — interface is fine, some features missing."),
    ]


def test_sentiment_classifies_majority_correctly(labeled_reviews: list[Review]) -> None:
    """Sentiment model should agree with star ratings on the obvious cases."""
    classifications = svc.classify_sentiments(labeled_reviews)
    assert len(classifications) == len(labeled_reviews)

    # The clearly-negative 1★ reviews should land in {VERY_NEGATIVE, NEGATIVE}.
    for review_id in ("r0", "r1", "r4"):
        assert classifications[review_id] in NEGATIVE_CLASSES, (
            f"{review_id} expected negative, got {classifications[review_id]}"
        )

    # The clearly-positive 5★ reviews should be positive.
    positives = {SentimentClass.POSITIVE, SentimentClass.VERY_POSITIVE}
    for review_id in ("r5", "r6"):
        assert classifications[review_id] in positives, (
            f"{review_id} expected positive, got {classifications[review_id]}"
        )


def test_breakdown_totals_match_input(labeled_reviews: list[Review]) -> None:
    classifications = svc.classify_sentiments(labeled_reviews)
    breakdown = svc.compute_sentiment_breakdown(classifications)
    assert breakdown.total == len(labeled_reviews)
    assert sum(breakdown.counts.values()) == len(labeled_reviews)
    assert sum(breakdown.percentages.values()) == pytest.approx(100.0, abs=0.1)


def test_full_report_runs_end_to_end(labeled_reviews: list[Review]) -> None:
    """Smoke check the orchestrator produces a well-formed report."""
    report = svc.compute_insights_report(labeled_reviews)

    assert report.sentiment_breakdown.total == len(labeled_reviews)
    # We have clearly-negative reviews, so there should be at least one negative.
    n_negative = (
        report.sentiment_breakdown.counts[SentimentClass.VERY_NEGATIVE]
        + report.sentiment_breakdown.counts[SentimentClass.NEGATIVE]
    )
    assert n_negative >= 3
    # Themes + insights may be empty if BERTopic can't cluster this few docs;
    # we don't assert structure beyond "they're lists of the right type".
    assert isinstance(report.themes, list)
    assert isinstance(report.insights, list)
    print(
        f"\n  Sentiment: {dict(report.sentiment_breakdown.counts)}\n"
        f"  Themes: {len(report.themes)}\n"
        f"  Insights: {len(report.insights)}"
    )
