from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["dev", "prod", "test"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:8080"]
    )

    database_url: str = "sqlite+aiosqlite:///./data/reviews.db"

    # Local HuggingFace NLP models. Switch to tabularisai/multilingual-sentiment-analysis
    # for better Ukrainian/Russian coverage. See docs/nlp-analysis.md.
    sentiment_model: str = "nlptown/bert-base-multilingual-uncased-sentiment"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    hf_cache_dir: str | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
