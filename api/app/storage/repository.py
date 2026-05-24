"""SQLite-backed persistence for collected reviews and computed insights."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

from app.models.domain import InsightsReport, Review

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS reviews (
    app_id      INTEGER NOT NULL,
    country     TEXT    NOT NULL,
    id          TEXT    NOT NULL,
    title       TEXT    NOT NULL,
    body        TEXT    NOT NULL,
    rating      INTEGER NOT NULL,
    author      TEXT    NOT NULL,
    created_at  TEXT    NOT NULL,
    is_edited   INTEGER NOT NULL,
    collected_at TEXT   NOT NULL,
    PRIMARY KEY (app_id, country, id)
);

CREATE INDEX IF NOT EXISTS idx_reviews_app_country ON reviews(app_id, country);

CREATE TABLE IF NOT EXISTS insights_reports (
    app_id      INTEGER NOT NULL,
    country     TEXT    NOT NULL,
    report_json TEXT    NOT NULL,
    computed_at TEXT    NOT NULL,
    PRIMARY KEY (app_id, country)
);

CREATE TABLE IF NOT EXISTS collections (
    app_id            INTEGER NOT NULL,
    country           TEXT    NOT NULL,
    last_collected_at TEXT    NOT NULL,
    review_count      INTEGER NOT NULL,
    PRIMARY KEY (app_id, country)
);
"""


def _db_path_from_url(url: str) -> str:
    prefix = "sqlite+aiosqlite:///"
    if url.startswith(prefix):
        return url[len(prefix) :]
    if url.startswith("sqlite:///"):
        return url[len("sqlite:///") :]
    return url


class ReviewRepository:
    def __init__(self, database_url: str) -> None:
        self._path = _db_path_from_url(database_url)
        if self._path and self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._initialized = False

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[aiosqlite.Connection]:
        async with aiosqlite.connect(self._path) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA foreign_keys = ON")
            yield conn

    async def initialize(self) -> None:
        if self._initialized:
            return
        async with self._connect() as conn:
            await conn.executescript(_SCHEMA_SQL)
            await conn.commit()
        self._initialized = True

    async def save_reviews(self, reviews: list[Review]) -> None:
        if not reviews:
            return
        await self.initialize()
        now = datetime.now(UTC).isoformat()
        rows = [
            (
                r.app_id,
                r.country,
                r.id,
                r.title,
                r.body,
                r.rating,
                r.author,
                r.created_at.isoformat(),
                int(r.is_edited),
                now,
            )
            for r in reviews
        ]
        async with self._connect() as conn:
            await conn.executemany(
                """
                INSERT OR REPLACE INTO reviews
                (app_id, country, id, title, body, rating, author, created_at, is_edited, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            await conn.commit()

    async def list_reviews(self, app_id: int, country: str) -> list[Review]:
        await self.initialize()
        async with self._connect() as conn:
            cursor = await conn.execute(
                """
                SELECT id, title, body, rating, author, created_at, is_edited
                FROM reviews
                WHERE app_id = ? AND country = ?
                ORDER BY created_at DESC
                """,
                (app_id, country),
            )
            rows = await cursor.fetchall()
        return [
            Review(
                id=row["id"],
                app_id=app_id,
                country=country,
                title=row["title"],
                body=row["body"],
                rating=row["rating"],
                author=row["author"],
                created_at=datetime.fromisoformat(row["created_at"]),
                is_edited=bool(row["is_edited"]),
            )
            for row in rows
        ]

    async def save_insights(self, app_id: int, country: str, report: InsightsReport) -> None:
        await self.initialize()
        async with self._connect() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO insights_reports
                (app_id, country, report_json, computed_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    app_id,
                    country,
                    report.model_dump_json(),
                    datetime.now(UTC).isoformat(),
                ),
            )
            await conn.commit()

    async def get_insights(self, app_id: int, country: str) -> InsightsReport | None:
        await self.initialize()
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT report_json FROM insights_reports WHERE app_id = ? AND country = ?",
                (app_id, country),
            )
            row = await cursor.fetchone()
        if not row:
            return None
        return InsightsReport.model_validate_json(row["report_json"])

    async def record_collection(self, app_id: int, country: str, count: int) -> datetime:
        await self.initialize()
        now = datetime.now(UTC)
        async with self._connect() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO collections
                (app_id, country, last_collected_at, review_count)
                VALUES (?, ?, ?, ?)
                """,
                (app_id, country, now.isoformat(), count),
            )
            await conn.commit()
        return now

    async def get_collection(self, app_id: int, country: str) -> dict[str, Any] | None:
        await self.initialize()
        async with self._connect() as conn:
            cursor = await conn.execute(
                """
                SELECT last_collected_at, review_count
                FROM collections WHERE app_id = ? AND country = ?
                """,
                (app_id, country),
            )
            row = await cursor.fetchone()
        if not row:
            return None
        return {
            "last_collected_at": datetime.fromisoformat(row["last_collected_at"]),
            "review_count": row["review_count"],
        }
