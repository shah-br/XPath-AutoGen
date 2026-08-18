"""Application configuration."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o", alias="OPENAI_MODEL")
    page_timeout_ms: int = Field(default=30_000, alias="PAGE_TIMEOUT_MS")
    llm_batch_size_classify: int = Field(default=25, alias="LLM_BATCH_SIZE_CLASSIFY")
    llm_batch_size_generate: int = Field(default=15, alias="LLM_BATCH_SIZE_GENERATE")
    max_elements: int = Field(default=200, alias="MAX_ELEMENTS")
    enable_hidden_discovery: bool = Field(default=True, alias="ENABLE_HIDDEN_DISCOVERY")
    output_dir: Path = Field(default=Path("output"), alias="OUTPUT_DIR")
    llm_concurrency: int = Field(default=3, alias="LLM_CONCURRENCY")
    browsers: list[str] = Field(default=["chromium", "firefox", "webkit"])

    @property
    def page_timeout_secs(self) -> float:
        return self.page_timeout_ms / 1000.0


def get_settings() -> Settings:
    return Settings()
