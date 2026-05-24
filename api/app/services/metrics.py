from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from app.models.domain import Metrics, RatingBucket, Review

RATING_VALUES: tuple[int, int, int, int, int] = (1, 2, 3, 4, 5)


def compute_metrics(reviews: Iterable[Review]) -> Metrics:
    """
    Pure aggregation over a list of reviews.

    - `total_reviews` — number of reviews provided.
    - `average_rating` — arithmetic mean, rounded to 2 decimals. 0.0 when empty.
    - `distribution` — always five buckets, one per star (1 to 5), each with count and percentage of total.
    """
    counts: Counter[int] = Counter()
    rating_sum = 0
    total = 0
    for review in reviews:
        rating_sum += review.rating
        counts[review.rating] += 1
        total += 1

    average = round(rating_sum / total, 2) if total else 0.0
    distribution = [
        RatingBucket(
            rating=star,
            count=counts.get(star, 0),
            percentage=round(counts.get(star, 0) / total * 100, 2) if total else 0.0,
        )
        for star in RATING_VALUES
    ]
    return Metrics(total_reviews=total, average_rating=average, distribution=distribution)
