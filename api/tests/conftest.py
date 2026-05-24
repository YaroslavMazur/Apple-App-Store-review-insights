from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Per-test isolated SQLite file so the repository persists across method calls."""
    db_path = tmp_path / "test.sqlite"
    return Settings(
        env="test",
        log_level="WARNING",
        database_url=f"sqlite+aiosqlite:///{db_path}",
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app) as c:
        yield c
