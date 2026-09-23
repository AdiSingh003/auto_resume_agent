"""Configuration management for the Auto Resume Agent."""

import os
import logging
from pydantic_settings import BaseSettings
from pydantic import Field

logger = logging.getLogger(__name__)


def _resolve_secret(env_var: str) -> str:
    """Resolve secret from environment or file; empty string if unset (.env is applied by pydantic-settings)."""
    value = os.environ.get(env_var)
    if value:
        return value

    secret_file = f"{env_var.lower()}.txt"
    if os.path.exists(secret_file):
        with open(secret_file, "r") as f:
            return f.read().strip()

    logger.info("%s is not set; the feature that needs it is disabled.", env_var)
    return ""


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # LLM Keys
    groq_api_key: str = Field(default_factory=lambda: _resolve_secret("GROQ_API_KEY"))
    google_api_key: str = Field(
        default_factory=lambda: _resolve_secret("GOOGLE_API_KEY")
    )
    tavily_api_key: str = Field(
        default_factory=lambda: _resolve_secret("TAVILY_API_KEY")
    )

    # Model config
    groq_model: str = "llama-3.3-70b-versatile"
    google_model: str = "gemini-2.0-flash"

    # Agent config
    max_revision_cycles: int = 3
    ats_score_threshold: int = 75
    formatting_score_threshold: int = 80
    factual_score_threshold: int = 90

    # Server config
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Paths
    output_dir: str = "output"
    upload_dir: str = "uploads"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
