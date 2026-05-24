"""FastAPI dependency providers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.config import Settings, get_settings
from app.storage.repository import ReviewRepository


def get_repository(request: Request) -> ReviewRepository:
    """Return the per-app singleton ReviewRepository stored on app state."""
    repo: ReviewRepository = request.app.state.repository
    return repo


SettingsDep = Annotated[Settings, Depends(get_settings)]
RepositoryDep = Annotated[ReviewRepository, Depends(get_repository)]
