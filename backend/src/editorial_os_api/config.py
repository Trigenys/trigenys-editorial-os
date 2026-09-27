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


@lru_cache
def get_settings() -> Settings:
    return Settings()
