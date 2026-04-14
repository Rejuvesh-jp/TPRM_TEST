import logging
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache

_log = logging.getLogger("tprm.config")


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "TPRM AI Assessment Platform"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production"

    # Separate API key for X-API-Key header auth (distinct from SECRET_KEY)
    # Leave empty to disable the core FastAPI API-key-protected routes.
    API_KEY: str = ""

    # Database
    POSTGRES_USER: str = "tprm_user"
    POSTGRES_PASSWORD: str = "tprm_password"
    POSTGRES_DB: str = "tprm_db"
    POSTGRES_HOST: str = "127.0.0.1"
    POSTGRES_PORT: int = 5432

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def SYNC_DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = 1536

    # File Upload
    MAX_UPLOAD_SIZE_MB: int = 100
    UPLOAD_DIR: str = "uploads"
    ALLOWED_EXTENSIONS: list[str] = [".pdf", ".docx", ".txt", ".csv", ".xlsx", ".json"]

    # Processing
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    MAX_RETRIES: int = 3

    model_config = {"env_file": ".env", "extra": "ignore"}

    def validate_secrets(self) -> None:
        """Log warnings for any settings still at insecure defaults."""
        if self.SECRET_KEY == "change-me-in-production":
            _log.critical(
                "SECRET_KEY is using the default value! "
                "Set a cryptographically random value in .env"
            )
        if self.POSTGRES_PASSWORD == "tprm_password":
            _log.warning(
                "POSTGRES_PASSWORD is using the default value — "
                "change it in .env for production deployments."
            )
        if not self.OPENAI_API_KEY:
            _log.warning("OPENAI_API_KEY is not set; LLM features will be unavailable.")


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.validate_secrets()
    return s
