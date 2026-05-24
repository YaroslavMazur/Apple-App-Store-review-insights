"""Integration tests for /api/v1/reviews/* endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models.domain import (
    Insight,
    InsightsReport,
    Review,
    SentimentBreakdown,
    SentimentClass,
    Theme,
)


def _review(rating: int, idx: int) -> Review:
    return Review(
        id=f"r{idx}",
        app_id=324684580,
        country="us",
        title=f"title {idx}",
        body=f"body {idx}",
        rating=rating,
        author=f"author{idx}",
        created_at=datetime(2025, 1, idx + 1, tzinfo=UTC),
        is_edited=False,
    )


def _fake_report() -> InsightsReport:
    return InsightsReport(
        sentiment_breakdown=SentimentBreakdown(
            counts={
                SentimentClass.VERY_NEGATIVE: 1,
                SentimentClass.NEGATIVE: 1,
                SentimentClass.NEUTRAL: 0,
                SentimentClass.POSITIVE: 1,
                SentimentClass.VERY_POSITIVE: 1,
            },
            percentages={
                SentimentClass.VERY_NEGATIVE: 25.0,
                SentimentClass.NEGATIVE: 25.0,
                SentimentClass.NEUTRAL: 0.0,
                SentimentClass.POSITIVE: 25.0,
                SentimentClass.VERY_POSITIVE: 25.0,
            },
            total=4,
        ),
        themes=[
            Theme(
                id=0,
                label="crashes, bugs",
                keywords=["crashes", "bugs", "freeze"],
                review_ids=["r0", "r1"],
                total_reviews=2,
                negative_count=2,
                negative_share=100.0,
                share_of_negatives=100.0,
                average_rating=1.5,
                is_pain_point=True,
            )
        ],
        insights=[
            Insight(
                title="crashes, bugs",
                severity="high",
                evidence_count=2,
                theme_id=0,
                suggestion="Investigate complaints around crashes, bugs.",
            )
        ],
    )


@pytest.fixture
def sample_reviews() -> list[Review]:
    return [_review(1, 0), _review(2, 1), _review(4, 2), _review(5, 3)]


@pytest.fixture
def mocked_pipeline(sample_reviews: list[Review]):
    """Patch fetcher + insights so no live App Store / model load happens in tests."""
    with (
        patch(
            "app.api.v1.reviews.fetch_reviews",
            new=AsyncMock(return_value=sample_reviews),
        ) as mock_fetch,
        patch(
            "app.api.v1.reviews.compute_insights_report",
            return_value=_fake_report(),
        ) as mock_insights,
    ):
        yield mock_fetch, mock_insights


# ── /collect ──────────────────────────────────────────────────────────────────


def test_collect_happy_path(
    client: TestClient,
    sample_reviews: list[Review],
    mocked_pipeline: tuple,
) -> None:
    response = client.post(
        "/api/v1/reviews/collect",
        json={"app_id": 324684580, "country": "us"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["app_id"] == 324684580
    assert body["country"] == "us"
    assert body["review_count"] == len(sample_reviews)
    assert body["metrics"]["total_reviews"] == len(sample_reviews)
    assert body["metrics"]["average_rating"] == 3.0
    assert len(body["metrics"]["distribution"]) == 5
    assert body["insights"]["themes"][0]["label"] == "crashes, bugs"


def test_collect_invalid_country_returns_400(client: TestClient, mocked_pipeline: tuple) -> None:
    response = client.post("/api/v1/reviews/collect", json={"app_id": 1, "country": "USA"})
    assert response.status_code == 422  # Pydantic validation


def test_collect_invalid_app_id_returns_422(client: TestClient, mocked_pipeline: tuple) -> None:
    response = client.post("/api/v1/reviews/collect", json={"app_id": -1, "country": "us"})
    assert response.status_code == 422


def test_collect_normalizes_country_to_lowercase(
    client: TestClient, mocked_pipeline: tuple
) -> None:
    response = client.post("/api/v1/reviews/collect", json={"app_id": 1, "country": "US"})
    assert response.status_code == 200
    assert response.json()["country"] == "us"


# ── /metrics ──────────────────────────────────────────────────────────────────


def test_metrics_404_when_not_collected(client: TestClient) -> None:
    response = client.get("/api/v1/reviews/324684580/metrics?country=us")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "app_not_found"


def test_metrics_returns_persisted_data_after_collect(
    client: TestClient, mocked_pipeline: tuple
) -> None:
    client.post("/api/v1/reviews/collect", json={"app_id": 324684580, "country": "us"})
    response = client.get("/api/v1/reviews/324684580/metrics?country=us")
    assert response.status_code == 200
    body = response.json()
    assert body["app_id"] == 324684580
    assert body["country"] == "us"
    assert body["metrics"]["total_reviews"] == 4
    assert body["metrics"]["average_rating"] == 3.0
    assert "last_collected_at" in body


# ── /insights ─────────────────────────────────────────────────────────────────


def test_insights_404_when_not_collected(client: TestClient) -> None:
    response = client.get("/api/v1/reviews/324684580/insights?country=us")
    assert response.status_code == 404


def test_insights_returns_persisted_report(client: TestClient, mocked_pipeline: tuple) -> None:
    client.post("/api/v1/reviews/collect", json={"app_id": 324684580, "country": "us"})
    response = client.get("/api/v1/reviews/324684580/insights?country=us")
    assert response.status_code == 200
    body = response.json()
    assert body["insights"]["sentiment_breakdown"]["total"] == 4
    assert body["insights"]["insights"][0]["severity"] == "high"
    assert body["insights"]["themes"][0]["label"] == "crashes, bugs"


# ── /raw ──────────────────────────────────────────────────────────────────────


def test_raw_json_default(client: TestClient, mocked_pipeline: tuple) -> None:
    client.post("/api/v1/reviews/collect", json={"app_id": 324684580, "country": "us"})
    response = client.get("/api/v1/reviews/324684580/raw?country=us")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert len(body["reviews"]) == 4
    assert body["reviews"][0]["app_id"] == 324684580


def test_raw_csv_download(client: TestClient, mocked_pipeline: tuple) -> None:
    client.post("/api/v1/reviews/collect", json={"app_id": 324684580, "country": "us"})
    response = client.get("/api/v1/reviews/324684580/raw?country=us&format=csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    csv_text = response.text
    assert csv_text.startswith("id,rating,title,body,author,created_at,is_edited")
    # Header + 4 data rows.
    assert len(csv_text.strip().splitlines()) == 5


def test_raw_404_when_not_collected(client: TestClient) -> None:
    response = client.get("/api/v1/reviews/999/raw?country=us")
    assert response.status_code == 404


# ── OpenAPI surface ───────────────────────────────────────────────────────────


def test_openapi_lists_all_four_endpoints(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert "/api/v1/reviews/collect" in paths
    assert "/api/v1/reviews/{app_id}/metrics" in paths
    assert "/api/v1/reviews/{app_id}/insights" in paths
    assert "/api/v1/reviews/{app_id}/raw" in paths
