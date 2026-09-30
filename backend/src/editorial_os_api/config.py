from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded exclusively from environment-compatible sources."""

    model_config = SettingsConfigDict(
        env_prefix="EDITORIAL_OS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Trigenys Editorial OS API"
    environment: Literal["development", "test", "production"] = "development"
    database_url: str = (
        "postgresql+psycopg://editorial_os:editorial_os@localhost:5432/editorial_os"
    )
    database_echo: bool = False
    langfuse_enabled: bool = False
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_base_url: str = "https://cloud.langfuse.com"
    langfuse_capture_model_io: bool = False
    posthog_enabled: bool = False
    posthog_project_token: str | None = None
    posthog_host: str = "https://us.i.posthog.com"
    payload_enabled: bool = False
    payload_base_url: str | None = None
    payload_api_token: str | None = None
    payload_collection: str = "posts"


@lru_cache
def get_settings() -> Settings:
    return Settings()
