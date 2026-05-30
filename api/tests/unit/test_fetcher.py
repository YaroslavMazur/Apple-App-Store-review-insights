from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.exceptions import AppNotFoundError, InvalidInputError, UpstreamUnavailableError
from app.models.domain import Review
from app.services.fetcher import _MAX_PAGE_ATTEMPTS, _PAGE_SIZE, fetch_all_reviews

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_reviews.json"


@pytest.fixture(autouse=True)
def _no_sleep() -> Iterator[None]:
    """Skip real throttling/backoff sleeps so the paging tests run instantly."""
    with patch("app.services.fetcher.time.sleep"):
        yield


@dataclass(frozen=True)
class FakeReview:
    """Test double that matches the _ReviewLike protocol."""

    id: str
    title: str
    content: str
    rating: int
    username: str
    date: datetime
    is_edited: bool


def _load_fixture() -> list[FakeReview]:
    raw = json.loads(FIXTURE.read_text())
    return [
        FakeReview(
            id=item["id"],
            title=item["title"],
            content=item["content"],
            rating=item["rating"],
            username=item["username"],
            date=datetime.fromisoformat(item["date"]),
            is_edited=item["is_edited"],
        )
        for item in raw
    ]


def _make_get_app(reviews: list[FakeReview], next_offset: int | None = None) -> MagicMock:
    """Build a mock get_app(...) callable returning an App-like object (single page)."""
    app = MagicMock()
    app.get_reviews.return_value = (reviews, next_offset)
    return MagicMock(return_value=app)


async def test_fetch_all_reviews_happy_path() -> None:
    reviews = _load_fixture()
    get_app = _make_get_app(reviews)

    with patch("app.services.fetcher.appstorescraper.get_app", get_app):
        result = await fetch_all_reviews(app_id=324684580, country="us")

    get_app.assert_called_once_with(app_id=324684580, country="us")
    # We drive paging ourselves: first batch is count=_PAGE_SIZE at offset 0.
    app_obj = get_app.return_value
    app_obj.get_reviews.assert_called_once_with(count=_PAGE_SIZE, offset=0)

    assert len(result) == 5
    assert all(isinstance(r, Review) for r in result)

    first = result[0]
    assert first.id == "11234567890"
    assert first.title == "Mixer is amazing"
    assert first.body.startswith("Love the new playlist mixer")
    assert first.rating == 5
    assert first.author == "music_fan_42"
    assert first.app_id == 324684580
    assert first.country == "us"
    assert first.is_edited is False

    edited = next(r for r in result if r.author == "frustrated_user")
    assert edited.is_edited is True
    assert edited.rating == 1


async def test_fetch_all_reviews_paginates_until_offset_none() -> None:
    """Follow Apple's next-offset cursor across multiple batches until it is None."""
    fixture = _load_fixture()
    page1, page2 = fixture[:3], fixture[3:]
    app = MagicMock()
    app.get_reviews.side_effect = [(page1, 100), (page2, None)]
    get_app = MagicMock(return_value=app)

    with patch("app.services.fetcher.appstorescraper.get_app", get_app):
        result = await fetch_all_reviews(app_id=1, country="us")

    assert len(result) == 5
    assert app.get_reviews.call_count == 2
    app.get_reviews.assert_any_call(count=_PAGE_SIZE, offset=0)
    app.get_reviews.assert_any_call(count=_PAGE_SIZE, offset=100)


async def test_fetch_all_reviews_uses_real_apple_id() -> None:
    """Review.id should be the real Apple-assigned id, not synthesized."""
    reviews = _load_fixture()
    with patch("app.services.fetcher.appstorescraper.get_app", _make_get_app(reviews)):
        result = await fetch_all_reviews(app_id=324684580, country="us")

    assert [r.id for r in result] == [
        "11234567890",
        "11234567891",
        "11234567892",
        "11234567893",
        "11234567894",
    ]


async def test_fetch_all_reviews_normalizes_missing_author_and_title() -> None:
    fake = [
        FakeReview(
            id="x",
            title="",
            content="no title, no name",
            rating=3,
            username="",
            date=datetime(2025, 1, 1, 12, 0, 0),
            is_edited=False,
        )
    ]
    with patch("app.services.fetcher.appstorescraper.get_app", _make_get_app(fake)):
        result = await fetch_all_reviews(app_id=1, country="us")

    assert result[0].author == "anonymous"
    assert result[0].title == ""


async def test_fetch_all_reviews_normalizes_country_to_lowercase() -> None:
    with patch("app.services.fetcher.appstorescraper.get_app", _make_get_app(_load_fixture())) as m:
        result = await fetch_all_reviews(app_id=1, country="US")
    m.assert_called_once_with(app_id=1, country="us")
    assert all(r.country == "us" for r in result)


async def test_fetch_all_reviews_empty_raises_app_not_found() -> None:
    with (
        patch("app.services.fetcher.appstorescraper.get_app", _make_get_app([])),
        pytest.raises(AppNotFoundError),
    ):
        await fetch_all_reviews(app_id=999999999, country="us")


async def test_fetch_all_reviews_no_reviews_for_country_raises_app_not_found() -> None:
    """Library raises ValueError('No reviews found...') for an unavailable country."""
    app = MagicMock()
    app.get_reviews.side_effect = ValueError("No reviews found for country code zz")
    with (
        patch("app.services.fetcher.appstorescraper.get_app", MagicMock(return_value=app)),
        pytest.raises(AppNotFoundError),
    ):
        await fetch_all_reviews(app_id=1, country="zz")
    # Should not be retried — it is a definitive "no data" signal.
    assert app.get_reviews.call_count == 1


async def test_fetch_all_reviews_invalid_country() -> None:
    with pytest.raises(InvalidInputError, match="country"):
        await fetch_all_reviews(app_id=1, country="USA")


async def test_fetch_all_reviews_invalid_app_id() -> None:
    with pytest.raises(InvalidInputError, match="app_id"):
        await fetch_all_reviews(app_id=0, country="us")
    with pytest.raises(InvalidInputError, match="app_id"):
        await fetch_all_reviews(app_id=-5, country="us")


async def test_fetch_all_reviews_lookup_failure_raises_upstream() -> None:
    """A failure in get_app (app lookup) surfaces as UpstreamUnavailableError."""

    def factory(*args: Any, **kwargs: Any) -> MagicMock:
        raise RuntimeError("app lookup blew up")

    with (
        patch("app.services.fetcher.appstorescraper.get_app", side_effect=factory),
        pytest.raises(UpstreamUnavailableError),
    ):
        await fetch_all_reviews(app_id=1, country="us")


async def test_fetch_all_reviews_batch_retries_then_succeeds() -> None:
    """A batch raises twice then succeeds — per-batch backoff should retry."""
    reviews = _load_fixture()
    app = MagicMock()
    app.get_reviews.side_effect = [
        RuntimeError("transient blip"),
        RuntimeError("transient blip"),
        (reviews, None),
    ]
    with patch("app.services.fetcher.appstorescraper.get_app", MagicMock(return_value=app)):
        result = await fetch_all_reviews(app_id=1, country="us")

    assert app.get_reviews.call_count == 3
    assert len(result) == 5


async def test_fetch_all_reviews_gives_up_after_max_attempts() -> None:
    """First batch never succeeds and nothing was collected → UpstreamUnavailableError."""
    app = MagicMock()
    app.get_reviews.side_effect = RuntimeError("persistent upstream failure")
    with (
        patch("app.services.fetcher.appstorescraper.get_app", MagicMock(return_value=app)),
        pytest.raises(UpstreamUnavailableError),
    ):
        await fetch_all_reviews(app_id=1, country="us")
    assert app.get_reviews.call_count == _MAX_PAGE_ATTEMPTS


async def test_fetch_all_reviews_returns_partial_when_later_batch_fails() -> None:
    """If a later batch fails after backoff, keep the reviews already collected."""
    fixture = _load_fixture()
    app = MagicMock()
    app.get_reviews.side_effect = [
        (fixture, 100),  # first batch OK, more pages remain
        RuntimeError("rate limited"),  # second batch fails every attempt
        RuntimeError("rate limited"),
        RuntimeError("rate limited"),
        RuntimeError("rate limited"),
    ]
    with patch("app.services.fetcher.appstorescraper.get_app", MagicMock(return_value=app)):
        result = await fetch_all_reviews(app_id=1, country="us")

    # We keep the first batch rather than throwing it all away.
    assert len(result) == 5
    # One successful batch + _MAX_PAGE_ATTEMPTS failed attempts on the second.
    assert app.get_reviews.call_count == 1 + _MAX_PAGE_ATTEMPTS
