from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.models.domain import Review
from app.services.metrics import compute_metrics


def _make_review(rating: int, idx: int = 0) -> Review:
    return Review(
        id=f"r{idx}",
        app_id=1,
        country="us",
        title="t",
        body="b",
        rating=rating,
        author="a",
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        is_edited=False,
    )


def test_empty_returns_zero_average_and_zero_buckets() -> None:
    metrics = compute_metrics([])
    assert metrics.total_reviews == 0
    assert metrics.average_rating == 0.0
    assert [b.rating for b in metrics.distribution] == [1, 2, 3, 4, 5]
    assert all(b.count == 0 and b.percentage == 0.0 for b in metrics.distribution)


def test_single_review() -> None:
    metrics = compute_metrics([_make_review(4)])
    assert metrics.total_reviews == 1
    assert metrics.average_rating == 4.0
    by_rating = {b.rating: b for b in metrics.distribution}
    assert by_rating[4].count == 1
    assert by_rating[4].percentage == 100.0
    for star in (1, 2, 3, 5):
        assert by_rating[star].count == 0
        assert by_rating[star].percentage == 0.0


def test_all_same_rating() -> None:
    metrics = compute_metrics([_make_review(5, i) for i in range(7)])
    assert metrics.total_reviews == 7
    assert metrics.average_rating == 5.0
    by_rating = {b.rating: b for b in metrics.distribution}
    assert by_rating[5].count == 7
    assert by_rating[5].percentage == 100.0


def test_mixed_ratings_average_and_distribution() -> None:
    # ratings: 1, 2, 3, 3, 4, 5, 5, 5  →  sum=28, n=8, avg=3.5
    ratings = [1, 2, 3, 3, 4, 5, 5, 5]
    metrics = compute_metrics([_make_review(r, i) for i, r in enumerate(ratings)])
    assert metrics.total_reviews == 8
    assert metrics.average_rating == 3.5

    expected_counts = {1: 1, 2: 1, 3: 2, 4: 1, 5: 3}
    for bucket in metrics.distribution:
        assert bucket.count == expected_counts[bucket.rating]
    # Percentages sum to 100 (within float epsilon).
    assert sum(b.percentage for b in metrics.distribution) == pytest.approx(100.0)


def test_distribution_always_has_five_buckets_sorted() -> None:
    metrics = compute_metrics([_make_review(3), _make_review(3, 1)])
    assert [b.rating for b in metrics.distribution] == [1, 2, 3, 4, 5]


def test_average_is_rounded_to_two_decimals() -> None:
    # ratings: 1, 2  →  avg 1.5 (clean); ratings 1,2,2 → 1.6666… → 1.67
    metrics = compute_metrics([_make_review(1), _make_review(2, 1), _make_review(2, 2)])
    assert metrics.average_rating == 1.67


def test_percentages_rounded_to_two_decimals() -> None:
    # 3 reviews, one 5★ → 33.33%
    metrics = compute_metrics([_make_review(1), _make_review(1, 1), _make_review(5, 2)])
    by_rating = {b.rating: b for b in metrics.distribution}
    assert by_rating[5].percentage == 33.33
    assert by_rating[1].percentage == 66.67


def test_accepts_generator() -> None:
    """compute_metrics should work with any Iterable, not just list."""
    reviews = (_make_review(r, i) for i, r in enumerate([5, 5, 1]))
    metrics = compute_metrics(reviews)
    assert metrics.total_reviews == 3
    assert metrics.average_rating == pytest.approx(11 / 3, abs=0.01)
