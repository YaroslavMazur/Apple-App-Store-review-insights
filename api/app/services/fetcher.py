from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

import anyio
import appstorescraper
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.exceptions import AppNotFoundError, InvalidInputError, UpstreamUnavailableError
from app.logging import get_logger
from app.models.domain import Review

logger = get_logger("fetcher")

MAX_LIMIT = 2000


class _ReviewLike(Protocol):
    @property
    def id(self) -> str: ...
    @property
    def title(self) -> str: ...
    @property
    def content(self) -> str: ...
    @property
    def rating(self) -> int: ...
    @property
    def username(self) -> str: ...
    @property
    def date(self) -> datetime: ...
    @property
    def is_edited(self) -> bool: ...


async def fetch_reviews(
    app_id: int,
    country: str,
    limit: int = 100,
) -> list[Review]:
    """
    Fetch up to `limit` recent reviews for the given App Store app.

    Args:
        app_id: numeric Apple app id (e.g. 324684580 for Spotify).
        country: ISO-3166-1 alpha-2 country code (lowercase or uppercase).
        limit: max reviews to retrieve, 1..500.

    Raises:
        InvalidInputError: validation failure on inputs.
        AppNotFoundError: app has no reviews / no reviews available for country.
        UpstreamUnavailableError: App Store request failed after retries.
    """
    _validate_inputs(app_id, country, limit)
    country_norm = country.lower()

    raw_reviews: list[_ReviewLike] = []
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
        retry=retry_if_exception_type(UpstreamUnavailableError),
        reraise=True,
    ):
        with attempt:
            raw_reviews = await anyio.to_thread.run_sync(_scrape_sync, app_id, country_norm, limit)

    if not raw_reviews:
        raise AppNotFoundError(
            "No reviews found for the given app",
            details={"app_id": app_id, "country": country_norm},
        )

    logger.info(
        "fetcher.success",
        count=len(raw_reviews),
        app_id=app_id,
        country=country_norm,
    )
    return [_normalize(r, app_id=app_id, country=country_norm) for r in raw_reviews]


def _validate_inputs(app_id: int, country: str, limit: int) -> None:
    if not isinstance(app_id, int) or app_id <= 0:
        raise InvalidInputError("app_id must be a positive integer")
    if len(country) != 2 or not country.isalpha():
        raise InvalidInputError("country must be a 2-letter ISO code")
    if not (1 <= limit <= MAX_LIMIT):
        raise InvalidInputError(f"limit must be between 1 and {MAX_LIMIT}")


def _scrape_sync(app_id: int, country: str, limit: int) -> list[_ReviewLike]:
    try:
        app = appstorescraper.get_app(app_id=app_id, country=country)
        reviews, _next_offset = app.get_reviews(count=limit, offset=0)
    except Exception as exc:
        raise UpstreamUnavailableError(
            f"App Store fetch failed: {exc}",
            details={"app_id": app_id, "country": country},
        ) from exc
    return list(reviews)


def _normalize(raw: _ReviewLike, *, app_id: int, country: str) -> Review:
    body = raw.content or ""
    author = (raw.username or "").strip() or "anonymous"
    title = (raw.title or "").strip()
    return Review(
        id=str(raw.id),
        app_id=app_id,
        country=country,
        title=title,
        body=body,
        rating=int(raw.rating),
        author=author,
        created_at=_coerce_datetime(raw.date),
        is_edited=bool(raw.is_edited),
    )


def _coerce_datetime(value: Any) -> datetime:
    # appstorescraperpy parses Apple's UTC timestamps with strptime and returns
    # naive datetimes; attach tzinfo=UTC so downstream serialization is correct.
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    raise UpstreamUnavailableError(f"Unexpected date type from scraper: {type(value).__name__}")
