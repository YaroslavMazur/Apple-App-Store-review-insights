from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any, Protocol

import anyio
import appstorescraper

from app.exceptions import AppNotFoundError, InvalidInputError, UpstreamUnavailableError
from app.logging import get_logger
from app.models.domain import Review

logger = get_logger("fetcher")

# Reviews fetched per upstream batch. The library pages 20 at a time internally;
# a batch of 100 keeps each internal burst short (5 requests) while limiting the
# number of round trips we drive from here.
_PAGE_SIZE = 100
# Polite pause between batches so we don't hammer Apple's API into a 429.
_PAGE_PAUSE_SECONDS = 1.0
# Backoff attempts for a single batch when Apple rate-limits or a transient
# network error hits. Base * 2**attempt → 5s, 10s, 20s.
_MAX_PAGE_ATTEMPTS = 4
_RATE_LIMIT_BASE_BACKOFF = 5.0


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


async def fetch_all_reviews(app_id: int, country: str) -> list[Review]:
    """
    Fetch every available review for the given App Store app.

    We drive pagination ourselves (rather than letting the library run
    `count=None` in one uninterrupted burst) so we can pause between batches
    and back off when Apple rate-limits. For very large apps this is slow but
    keeps the request rate under Apple's 429 threshold. If a batch ultimately
    fails after backoff but we have already collected reviews, we return the
    partial corpus instead of throwing it all away.

    Raises:
        InvalidInputError: validation failure on inputs.
        AppNotFoundError: app has no reviews / no reviews available for country.
        UpstreamUnavailableError: the very first batch failed (nothing collected).
    """
    _validate_inputs(app_id, country)
    country_norm = country.lower()

    raw_reviews = await anyio.to_thread.run_sync(_scrape_all_sync, app_id, country_norm)

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


def _validate_inputs(app_id: int, country: str) -> None:
    if not isinstance(app_id, int) or app_id <= 0:
        raise InvalidInputError("app_id must be a positive integer")
    if len(country) != 2 or not country.isalpha():
        raise InvalidInputError("country must be a 2-letter ISO code")


def _scrape_all_sync(app_id: int, country: str) -> list[_ReviewLike]:
    """Page through every review, throttling between batches and backing off on errors."""
    try:
        app = appstorescraper.get_app(app_id=app_id, country=country)
    except Exception as exc:
        raise UpstreamUnavailableError(
            f"App Store lookup failed: {exc}",
            details={"app_id": app_id, "country": country},
        ) from exc

    collected: list[_ReviewLike] = []
    offset: int | None = 0
    while offset is not None:
        try:
            page, next_offset = _fetch_one_page(app, offset, app_id, country)
        except AppNotFoundError:
            # Apple reports no reviews for this country — only meaningful on the
            # first batch; if we already have reviews we simply stop.
            if collected:
                break
            raise
        except UpstreamUnavailableError:
            if collected:
                logger.warning(
                    "fetcher.partial",
                    collected=len(collected),
                    stopped_at_offset=offset,
                    app_id=app_id,
                    country=country,
                )
                break
            raise

        collected.extend(page)
        if next_offset is None or not page:
            break
        offset = next_offset
        time.sleep(_PAGE_PAUSE_SECONDS)

    return collected


def _fetch_one_page(
    app: Any, offset: int, app_id: int, country: str
) -> tuple[list[_ReviewLike], int | None]:
    """Fetch a single batch with exponential backoff on rate limits / transient errors."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_PAGE_ATTEMPTS):
        try:
            reviews, next_offset = app.get_reviews(count=_PAGE_SIZE, offset=offset)
            return list(reviews), next_offset
        except Exception as exc:  # library raises bare requests/ValueError types
            if _is_no_reviews(exc):
                raise AppNotFoundError(
                    "No reviews found for the given app",
                    details={"app_id": app_id, "country": country},
                ) from exc
            last_exc = exc
            if attempt < _MAX_PAGE_ATTEMPTS - 1:
                backoff = _RATE_LIMIT_BASE_BACKOFF * (2**attempt)
                logger.warning(
                    "fetcher.batch_retry",
                    offset=offset,
                    attempt=attempt + 1,
                    backoff_seconds=backoff,
                    error=str(exc),
                    app_id=app_id,
                    country=country,
                )
                time.sleep(backoff)

    raise UpstreamUnavailableError(
        f"App Store fetch failed at offset {offset}: {last_exc}",
        details={"app_id": app_id, "country": country, "offset": offset},
    ) from last_exc


def _is_no_reviews(exc: Exception) -> bool:
    # The library raises ValueError("No reviews found for country code ...") when
    # Apple's availability check returns non-200 for the country.
    return isinstance(exc, ValueError) and "no reviews found" in str(exc).lower()


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
