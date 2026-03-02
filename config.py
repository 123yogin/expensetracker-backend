"""
Centralized Configuration Module
=================================
Loads all config from environment variables with validation.
No hardcoded secrets. No .env file parsing in production.
Uses python-dotenv only in development for convenience.
"""

import os
import secrets
from functools import lru_cache


class _ConfigError(Exception):
    """Raised when a required configuration value is missing."""
    pass


def _require_env(key: str) -> str:
    """Get a required environment variable or raise an error."""
    value = os.environ.get(key)
    if not value:
        raise _ConfigError(
            f"Required environment variable '{key}' is not set. "
            f"Check your .env file or deployment environment."
        )
    return value


def _get_env(key: str, default: str = "") -> str:
    """Get an optional environment variable with a default."""
    return os.environ.get(key, default)


class Config:
    """Application configuration loaded from environment variables."""

    # ---------- Database ----------
    DATABASE_URL: str = ""
    DB_POOL_MIN_CONN: int = 2
    DB_POOL_MAX_CONN: int = 10

    # ---------- Flask ----------
    DEBUG: bool = False
    SECRET_KEY: str = ""
    PORT: int = 5001

    # ---------- CORS ----------
    FRONTEND_ORIGINS: list[str] = []

    # ---------- AWS Cognito ----------
    COGNITO_USER_POOL_ID: str = ""
    COGNITO_REGION: str = ""
    COGNITO_APP_CLIENT_ID: str = ""

    # ---------- File Storage ----------
    UPLOAD_FOLDER: str = "uploads/receipts"
    MAX_UPLOAD_SIZE_MB: int = 5

    # ---------- Rate Limiting ----------
    RATE_LIMIT_DEFAULT: str = "60/minute"
    RATE_LIMIT_AUTH: str = "10/minute"
    RATE_LIMIT_WRITE: str = "30/minute"

    # ---------- Logging ----------
    LOG_LEVEL: str = "INFO"

    def __init__(self):
        # Load .env file if present (development only)
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass  # python-dotenv not installed; expected in production

        # Required values
        self.DATABASE_URL = _require_env("DATABASE_URL")
        self.COGNITO_USER_POOL_ID = _require_env("COGNITO_USER_POOL_ID")
        self.COGNITO_REGION = _require_env("COGNITO_REGION")
        self.COGNITO_APP_CLIENT_ID = _require_env("COGNITO_APP_CLIENT_ID")

        # Optional with defaults
        self.DEBUG = _get_env("FLASK_DEBUG", "false").lower() in ("true", "1", "yes")
        self.SECRET_KEY = _get_env("FLASK_SECRET_KEY", "") or secrets.token_hex(32)
        self.PORT = int(_get_env("PORT", "5001"))
        self.LOG_LEVEL = _get_env("LOG_LEVEL", "INFO").upper()
        self.UPLOAD_FOLDER = _get_env("UPLOAD_FOLDER", "uploads/receipts")
        self.MAX_UPLOAD_SIZE_MB = int(_get_env("MAX_UPLOAD_SIZE_MB", "5"))

        # CORS origins (comma-separated)
        origins_str = _get_env("FRONTEND_ORIGINS", "http://localhost:5173")
        self.FRONTEND_ORIGINS = [o.strip() for o in origins_str.split(",") if o.strip()]

        # DB Pool
        self.DB_POOL_MIN_CONN = int(_get_env("DB_POOL_MIN_CONN", "2"))
        self.DB_POOL_MAX_CONN = int(_get_env("DB_POOL_MAX_CONN", "10"))

        # Rate limiting
        self.RATE_LIMIT_DEFAULT = _get_env("RATE_LIMIT_DEFAULT", "60/minute")
        self.RATE_LIMIT_AUTH = _get_env("RATE_LIMIT_AUTH", "10/minute")
        self.RATE_LIMIT_WRITE = _get_env("RATE_LIMIT_WRITE", "30/minute")

    @property
    def COGNITO_JWKS_URL(self) -> str:
        return (
            f"https://cognito-idp.{self.COGNITO_REGION}.amazonaws.com/"
            f"{self.COGNITO_USER_POOL_ID}/.well-known/jwks.json"
        )

    @property
    def COGNITO_ISSUER(self) -> str:
        return (
            f"https://cognito-idp.{self.COGNITO_REGION}.amazonaws.com/"
            f"{self.COGNITO_USER_POOL_ID}"
        )

    @property
    def MAX_UPLOAD_BYTES(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    def validate(self) -> list[str]:
        """Validate config and return list of warnings."""
        warnings = []
        if self.DEBUG:
            warnings.append("DEBUG mode is ON — disable for production")
        if "localhost" in self.DATABASE_URL:
            warnings.append("Database URL points to localhost — ensure this is correct for your environment")
        if not self.FRONTEND_ORIGINS:
            warnings.append("No FRONTEND_ORIGINS configured for CORS")
        return warnings


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Get the cached application configuration."""
    return Config()
