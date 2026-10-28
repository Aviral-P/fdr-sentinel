"""Environment-based application settings."""

from functools import lru_cache
from pathlib import Path
from pydantic import Field, SecretStr

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FDR Sentinel API"
    api_v1_prefix: str = "/api/v1"
    debug: bool = False
    app_env: str = "development"
    database_url: str = "sqlite:///./fdr_sentinel.db"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    jwt_secret_key: SecretStr = SecretStr("")
    jwt_access_token_minutes: int = Field(default=15, gt=0, le=60)
    jwt_issuer: str = "fdr-sentinel-local"
    document_storage_dir: Path = Path("./backend/data/documents")
    max_document_size_bytes: int = Field(default=15 * 1024 * 1024, gt=0, le=100 * 1024 * 1024)
    maturity_reminder_windows_days: str = "30,15,7"
    action_overdue_days: int = Field(default=7, gt=0, le=365)
    local_ocr_enabled: bool = False

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        """Return configured browser origins as a trimmed list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def maturity_reminder_window_list(self) -> list[int]:
        """Return unique positive maturity reminder windows, largest first."""
        try:
            windows = {int(value.strip()) for value in self.maturity_reminder_windows_days.split(",") if value.strip()}
        except ValueError as exc:
            raise ValueError("MATURITY_REMINDER_WINDOWS_DAYS must be comma-separated positive integers") from exc
        if not windows or any(window <= 0 for window in windows):
            raise ValueError("MATURITY_REMINDER_WINDOWS_DAYS must contain positive integers")
        return sorted(windows, reverse=True)

    @property
    def resolved_document_storage_dir(self) -> Path:
        """Resolve relative storage paths from the repository root, not process cwd."""
        if self.document_storage_dir.is_absolute():
            return self.document_storage_dir
        return Path(__file__).resolve().parents[3] / self.document_storage_dir


@lru_cache
def get_settings() -> Settings:
    """Cache settings so application components share one configuration."""
    return Settings()
