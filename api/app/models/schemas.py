"""API request/response schemas (Pydantic v2)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.domain import InsightsReport, Metrics, Review


class CollectRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"app_id": 324684580, "country": "us"}]},
    )

    app_id: int = Field(gt=0, description="Apple App Store numeric app id")
    country: str = Field(
        min_length=2,
        max_length=2,
        description="ISO-3166-1 alpha-2 country code (case-insensitive)",
    )
    limit: int = Field(
        default=100,
        ge=1,
        le=5000,
        description=(
            "Random sample size: the API always fetches every available review from "
            "the App Store, then picks this many uniformly at random for metrics + NLP "
            "analysis. If the app has fewer reviews than this, all are used."
        ),
    )


class CollectResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    app_id: int
    country: str
    collected_at: datetime
    review_count: int
    metrics: Metrics
    insights: InsightsReport


class MetricsResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    app_id: int
    country: str
    last_collected_at: datetime
    metrics: Metrics


class InsightsResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    app_id: int
    country: str
    last_collected_at: datetime
    insights: InsightsReport


class RawReviewsResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    app_id: int
    country: str
    last_collected_at: datetime
    reviews: list[Review]
