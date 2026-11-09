"""Application configuration loaded from environment / .env file."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Coco Automation"
    app_version: str = "0.1.0"
    environment: str = "production"

    host: str = "0.0.0.0"
    port: int = 8080

    database_url: str = "postgresql+psycopg://coco:coco@localhost:5432/coco"

    # Root folder for all generated/uploaded files (videos, images, audio ...)
    storage_dir: Path = PROJECT_ROOT / "storage"
    # Built frontend (vite build output)
    frontend_dist: Path = PROJECT_ROOT / "frontend" / "dist"

    # Fernet key used to encrypt OAuth tokens at rest. REQUIRED.
    secret_key: str = Field(default="", description="Fernet key (urlsafe base64, 32 bytes)")

    # Optional HTTP Basic auth for the dashboard (recommended on shared LAN)
    dashboard_username: str = "admin"
    dashboard_password: str = ""

    max_upload_mb: int = 25
    log_level: str = "INFO"
    log_dir: Path = PROJECT_ROOT / "logs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
