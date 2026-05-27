from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Review(BaseModel):
    """A single normalized App Store review."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Stable hash over (app_id, author, created_at, body[:200]).")
    app_id: int
    country: str = Field(min_length=2, max_length=2, description="ISO-3166-1 alpha-2, lowercase.")
    title: str
    body: str
    rating: int = Field(ge=1, le=5)
    author: str
    created_at: datetime
    is_edited: bool = False

    @property
    def text_hash(self) -> str:
        """SHA-256 of (title + body) — cache key for LLM outputs."""
        return sha256(f"{self.title}\n{self.body}".encode()).hexdigest()


def synthesize_review_id(app_id: int, author: str, created_at: datetime, body: str) -> str:
    payload = f"{app_id}|{author}|{created_at.isoformat()}|{body[:200]}"
    return sha256(payload.encode()).hexdigest()[:16]


class RatingBucket(BaseModel):
    """Count and share of reviews at a given star rating."""

    model_config = ConfigDict(frozen=True)

    rating: int = Field(ge=1, le=5)
    count: int = Field(ge=0)
    percentage: float = Field(ge=0.0, le=100.0)


class Metrics(BaseModel):
    """Aggregated rating statistics for a collected review set."""

    model_config = ConfigDict(frozen=True)

    total_reviews: int = Field(ge=0)
    average_rating: float = Field(ge=0.0, le=5.0)
    distribution: list[RatingBucket] = Field(
        description="Always 5 entries, one per star, sorted 1→5.",
    )


class SentimentClass(StrEnum):
    VERY_NEGATIVE = "very_negative"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"
    VERY_POSITIVE = "very_positive"


NEGATIVE_CLASSES: frozenset[SentimentClass] = frozenset(
    {SentimentClass.VERY_NEGATIVE, SentimentClass.NEGATIVE}
)


class SentimentBreakdown(BaseModel):
    """Aggregated sentiment counts and shares across all reviews."""

    model_config = ConfigDict(frozen=True)

    counts: dict[SentimentClass, int]
    percentages: dict[SentimentClass, float]
    total: int = Field(ge=0)


class Theme(BaseModel):
    """A cluster of semantically related reviews (derived from BERTopic)."""

    model_config = ConfigDict(frozen=True)

    id: int
    label: str
    keywords: list[str]
    review_ids: list[str]
    total_reviews: int = Field(ge=0)
    negative_count: int = Field(
        ge=0, description="Reviews in this theme that are negative or very negative"
    )
    negative_share: float = Field(
        ge=0.0,
        le=100.0,
        description="% of this theme's reviews that are negative — high values flag pain points",
    )
    share_of_negatives: float = Field(
        ge=0.0,
        le=100.0,
        description="% of ALL negative reviews that fell into this theme",
    )
    average_rating: float = Field(ge=0.0, le=5.0)
    is_pain_point: bool = Field(default=False, description="negative_share >= 50%")


class Insight(BaseModel):
    """An actionable suggestion derived from a theme."""

    model_config = ConfigDict(frozen=True)

    title: str
    severity: Literal["low", "medium", "high"]
    evidence_count: int = Field(ge=0)
    theme_id: int | None = None
    suggestion: str


class ReviewPoint(BaseModel):
    """One review's position in the 2D semantic map."""

    model_config = ConfigDict(frozen=True)

    review_id: str
    x: float
    y: float
    sentiment: SentimentClass
    rating: int = Field(ge=1, le=5)
    topic_id: int | None = None  # set only for negatives that landed in a theme


class InsightsReport(BaseModel):
    """End-to-end NLP output: sentiment + themes + suggestions + 2D map."""

    model_config = ConfigDict(frozen=True)

    sentiment_breakdown: SentimentBreakdown
    themes: list[Theme]
    insights: list[Insight]
    review_map: list[ReviewPoint] = Field(default_factory=list)
