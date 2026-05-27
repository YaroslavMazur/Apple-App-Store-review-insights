from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.exceptions import AppNotFoundError, InvalidInputError, UpstreamUnavailableError
from app.models.domain import Review
from app.services.fetcher import fetch_all_reviews

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_reviews.json"


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
    """Build a mock get_app(...) callable returning an App-like object."""
    app = MagicMock()
    app.get_reviews.return_value = (reviews, next_offset)
    return MagicMock(return_value=app)


async def test_fetch_all_reviews_happy_path() -> None:
    reviews = _load_fixture()
    get_app = _make_get_app(reviews)

    with patch("app.services.fetcher.appstorescraper.get_app", get_app):
        result = await fetch_all_reviews(app_id=324684580, country="us")

    get_app.assert_called_once_with(app_id=324684580, country="us")
    # appstorescraperpy must be called with count=None so it paginates exhaustively.
    app_obj = get_app.return_value
    app_obj.get_reviews.assert_called_once_with(count=None, offset=0)

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


async def test_fetch_all_reviews_invalid_country() -> None:
    with pytest.raises(InvalidInputError, match="country"):
        await fetch_all_reviews(app_id=1, country="USA")


async def test_fetch_all_reviews_invalid_app_id() -> None:
    with pytest.raises(InvalidInputError, match="app_id"):
        await fetch_all_reviews(app_id=0, country="us")
    with pytest.raises(InvalidInputError, match="app_id"):
        await fetch_all_reviews(app_id=-5, country="us")


async def test_fetch_all_reviews_retries_then_succeeds() -> None:
    """get_app raises twice, succeeds on third attempt — tenacity should retry."""
    reviews = _load_fixture()
    success_app = MagicMock()
    success_app.get_reviews.return_value = (reviews, None)

    call_count = {"n": 0}

    def factory(*args: Any, **kwargs: Any) -> MagicMock:
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise RuntimeError("transient upstream blip")
        return success_app

    with patch("app.services.fetcher.appstorescraper.get_app", side_effect=factory):
        result = await fetch_all_reviews(app_id=1, country="us")

    assert call_count["n"] == 3
    assert len(result) == 5


async def test_fetch_all_reviews_gives_up_after_max_retries() -> None:
    def factory(*args: Any, **kwargs: Any) -> MagicMock:
        raise RuntimeError("persistent upstream failure")

    with (
        patch("app.services.fetcher.appstorescraper.get_app", side_effect=factory),
        pytest.raises(UpstreamUnavailableError),
    ):
        await fetch_all_reviews(app_id=1, country="us")
