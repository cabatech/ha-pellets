"""Configuration via pydantic-settings (lit .env + env vars)."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration du service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="PELLETS_",
        extra="ignore",
    )

    # Base de données
    db_path: Path = Path("./data/pellets.db")

    # API
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"

    # Notion (optionnel, pour import initial)
    notion_token: str = ""
    notion_database_pellets_id: str = ""
    notion_database_calendrier_id: str = ""

    @property
    def db_url(self) -> str:
        """URL SQLite pour aiosqlite / sqlite3."""
        return f"sqlite:///{self.db_path}"


settings = Settings()
