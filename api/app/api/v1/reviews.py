"""Endpoints under /api/v1/reviews."""

from __future__ import annotations

import csv
import io
import json
import time
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal

import anyio
from fastapi import APIRouter, Path, Query
from fastapi.responses import StreamingResponse

from app.api.deps import RepositoryDep
from app.exceptions import AppNotFoundError, DomainError
from app.logging import get_logger
from app.models.domain import InsightsReport, Review, SentimentClass
from app.models.schemas import (
    CollectRequest,
    CollectResponse,
    InsightsResponse,
    MetricsResponse,
    RawReviewsResponse,
)
from app.services.fetcher import fetch_reviews
from app.services.insights import (
    build_review_map,
    classify_sentiments,
    cluster_all_reviews,
    compute_insights_report,
    compute_sentiment_breakdown,
    derive_actionable_insights,
    embed_all,
    reduce_to_2d,
)
from app.services.metrics import compute_metrics

router = APIRouter(prefix="/reviews", tags=["reviews"])
logger = get_logger("api.reviews")

AppIdPath = Annotated[int, Path(gt=0, description="Apple App Store numeric app id")]
CountryQ = Annotated[
    str, Query(min_length=2, max_length=2, description="ISO 3166-1 alpha-2 country code")
]


@router.post(
    "/collect",
    response_model=CollectResponse,
    summary="Fetch reviews for an app, compute metrics + NLP insights, persist.",
)
async def collect(
    request: CollectRequest,
    repo: RepositoryDep,
) -> CollectResponse:
    country = request.country.lower()
    logger.info("api.collect.start", app_id=request.app_id, country=country, limit=request.limit)

    reviews = await fetch_reviews(app_id=request.app_id, country=country, limit=request.limit)

    metrics = compute_metrics(reviews)
    # CPU-bound; run off the event loop.
    insights = await anyio.to_thread.run_sync(compute_insights_report, reviews)

    await repo.save_reviews(reviews)
    await repo.save_insights(request.app_id, country, insights)
    collected_at = await repo.record_collection(request.app_id, country, len(reviews))

    logger.info(
        "api.collect.done",
        app_id=request.app_id,
        country=country,
        review_count=len(reviews),
    )
    return CollectResponse(
        app_id=request.app_id,
        country=country,
        collected_at=collected_at,
        review_count=len(reviews),
        metrics=metrics,
        insights=insights,
    )


@router.post(
    "/collect/stream",
    response_class=StreamingResponse,
    summary="Same as /collect but streams NDJSON stage events as the pipeline runs.",
)
async def collect_stream(
    request: CollectRequest,
    repo: RepositoryDep,
) -> StreamingResponse:
    """Stream NDJSON stage events so the UI can render live pipeline progress."""
    country = request.country.lower()
    return StreamingResponse(
        _collect_pipeline_events(request, country, repo),
        media_type="application/x-ndjson",
    )


def _event(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, default=str) + "\n").encode("utf-8")


async def _collect_pipeline_events(
    request: CollectRequest,
    country: str,
    repo: Any,
) -> AsyncIterator[bytes]:
    started_at: dict[str, float] = {}

    def start(stage_id: str, label: str) -> bytes:
        started_at[stage_id] = time.monotonic()
        return _event(
            {"type": "stage", "id": stage_id, "state": "started", "label": label}
        )

    def done(stage_id: str, detail: str | None = None) -> bytes:
        duration_ms = int((time.monotonic() - started_at.pop(stage_id, time.monotonic())) * 1000)
        payload: dict[str, Any] = {
            "type": "stage",
            "id": stage_id,
            "state": "completed",
            "duration_ms": duration_ms,
        }
        if detail:
            payload["detail"] = detail
        return _event(payload)

    try:
        yield start("fetch", "Fetching reviews from the App Store")
        reviews = await fetch_reviews(
            app_id=request.app_id, country=country, limit=request.limit
        )
        yield done("fetch", detail=f"{len(reviews)} reviews")

        yield start("metrics", "Computing rating metrics")
        metrics = compute_metrics(reviews)
        yield done("metrics")

        yield start("sentiment", "Classifying sentiment with multilingual DistilBERT")
        classifications = await anyio.to_thread.run_sync(classify_sentiments, reviews)
        breakdown = compute_sentiment_breakdown(classifications)
        n_neg = (
            breakdown.counts.get(SentimentClass.NEGATIVE, 0)
            + breakdown.counts.get(SentimentClass.VERY_NEGATIVE, 0)
        )
        yield done("sentiment", detail=f"{n_neg} negative reviews")

        yield start("embed", "Embedding reviews with MiniLM")
        embeddings = await anyio.to_thread.run_sync(embed_all, reviews)
        coords_2d = await anyio.to_thread.run_sync(reduce_to_2d, embeddings)
        yield done("embed")

        yield start("cluster", "Clustering all reviews with BERTopic")
        themes, review_to_topic = await anyio.to_thread.run_sync(
            cluster_all_reviews, reviews, classifications, coords_2d
        )
        n_pain = sum(1 for t in themes if t.is_pain_point)
        yield done("cluster", detail=f"{len(themes)} themes ({n_pain} pain points)")

        yield start("map", "Building 2D semantic map")
        review_map = build_review_map(reviews, classifications, coords_2d, review_to_topic)
        yield done("map", detail=f"{len(review_map)} points")

        insights = derive_actionable_insights(themes)
        report = InsightsReport(
            sentiment_breakdown=breakdown,
            themes=themes,
            insights=insights,
            review_map=review_map,
        )

        yield start("persist", "Saving to database")
        await repo.save_reviews(reviews)
        await repo.save_insights(request.app_id, country, report)
        collected_at = await repo.record_collection(
            request.app_id, country, len(reviews)
        )
        yield done("persist")

        response = CollectResponse(
            app_id=request.app_id,
            country=country,
            collected_at=collected_at,
            review_count=len(reviews),
            metrics=metrics,
            insights=report,
        )
        yield _event({"type": "result", "data": json.loads(response.model_dump_json())})

    except DomainError as exc:
        logger.warning("api.collect_stream.domain_error", code=exc.code, message=exc.message)
        yield _event(
            {
                "type": "error",
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        )
    except Exception as exc:
        logger.exception("api.collect_stream.unexpected")
        yield _event(
            {
                "type": "error",
                "code": "internal_error",
                "message": f"Unexpected error: {exc}",
            }
        )


@router.get(
    "/{app_id}/metrics",
    response_model=MetricsResponse,
    summary="Rating metrics for a previously collected app.",
)
async def get_metrics(
    app_id: AppIdPath,
    repo: RepositoryDep,
    country: CountryQ = "us",
) -> MetricsResponse:
    country_norm = country.lower()
    collection = await repo.get_collection(app_id, country_norm)
    if not collection:
        raise AppNotFoundError(
            "App has not been collected yet — POST /api/v1/reviews/collect first.",
            details={"app_id": app_id, "country": country_norm},
        )
    reviews = await repo.list_reviews(app_id, country_norm)
    return MetricsResponse(
        app_id=app_id,
        country=country_norm,
        last_collected_at=collection["last_collected_at"],
        metrics=compute_metrics(reviews),
    )


@router.get(
    "/{app_id}/insights",
    response_model=InsightsResponse,
    summary="Sentiment + themes + actionable insights for a previously collected app.",
)
async def get_insights(
    app_id: AppIdPath,
    repo: RepositoryDep,
    country: CountryQ = "us",
) -> InsightsResponse:
    country_norm = country.lower()
    collection = await repo.get_collection(app_id, country_norm)
    report = await repo.get_insights(app_id, country_norm)
    if not collection or not report:
        raise AppNotFoundError(
            "Insights not available — POST /api/v1/reviews/collect first.",
            details={"app_id": app_id, "country": country_norm},
        )
    return InsightsResponse(
        app_id=app_id,
        country=country_norm,
        last_collected_at=collection["last_collected_at"],
        insights=report,
    )


@router.get(
    "/{app_id}/raw",
    response_model=None,  # response is union of JSON model + CSV stream
    summary="Raw collected reviews. Returns JSON by default, CSV when ?format=csv.",
)
async def get_raw(
    app_id: AppIdPath,
    repo: RepositoryDep,
    country: CountryQ = "us",
    format: Literal["json", "csv"] = Query(default="json", description="Output format"),
) -> RawReviewsResponse | StreamingResponse:
    country_norm = country.lower()
    collection = await repo.get_collection(app_id, country_norm)
    if not collection:
        raise AppNotFoundError(
            "App has not been collected yet — POST /api/v1/reviews/collect first.",
            details={"app_id": app_id, "country": country_norm},
        )
    reviews = await repo.list_reviews(app_id, country_norm)

    if format == "csv":
        return _reviews_to_csv(app_id, country_norm, reviews)

    return RawReviewsResponse(
        app_id=app_id,
        country=country_norm,
        last_collected_at=collection["last_collected_at"],
        reviews=reviews,
    )


def _reviews_to_csv(app_id: int, country: str, reviews: list[Review]) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "rating", "title", "body", "author", "created_at", "is_edited"])
    for r in reviews:
        writer.writerow(
            [
                r.id,
                r.rating,
                r.title,
                r.body,
                r.author,
                r.created_at.isoformat(),
                int(r.is_edited),
            ]
        )
    buf.seek(0)
    filename = f"reviews-{app_id}-{country}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
