
"""SoraLink application configuration."""

from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def _env_bool(name: str, default: bool = False) -> bool:
    """Parse a boolean environment variable safely."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    """Base configuration for the SoraLink Flask application."""

    # Application
    APP_NAME = "SoraLink"
    ENV = os.environ.get("SORALINK_ENV", "development").strip().lower()
    DEBUG = _env_bool("SORALINK_DEBUG", ENV == "development")
    TESTING = _env_bool("SORALINK_TESTING", False)

    # Flask session signing. Set a strong random value outside development.
    SECRET_KEY = os.environ.get("SORALINK_SECRET_KEY")
    if not SECRET_KEY:
        if ENV == "production":
            raise RuntimeError(
                "SORALINK_SECRET_KEY must be configured in production."
            )
        SECRET_KEY = "local-development-only-change-before-deployment"

    # SQLite database. database.py reads this same environment variable.
    DATABASE_PATH = Path(
        os.environ.get(
            "SORALINK_DB_PATH",
            str(BASE_DIR / "data" / "soralink.db"),
        )
    ).expanduser()

    # Authentication
    SESSION_TTL_SECONDS = int(
        os.environ.get("SORALINK_SESSION_TTL_SECONDS", str(8 * 60 * 60))
    )
    CREW_CODE = os.environ.get("SORALINK_CREW_CODE")

    # Local/offline server defaults.
    HOST = os.environ.get("SORALINK_HOST", "0.0.0.0")
    PORT = int(os.environ.get("SORALINK_PORT", "5000"))

    # Voice processing limits; actual processing is implemented separately.
    MAX_CONTENT_LENGTH = int(
        os.environ.get("SORALINK_MAX_UPLOAD_BYTES", str(15 * 1024 * 1024))
    )
    VOICE_PREVIEW_TTL_SECONDS = int(
        os.environ.get("SORALINK_VOICE_PREVIEW_TTL_SECONDS", str(30 * 60))
    )

    # Announcement limits.
    DEFAULT_BROADCAST_TTL_SECONDS = int(
        os.environ.get("SORALINK_BROADCAST_TTL_SECONDS", "120")
    )
    MAX_BROADCAST_TTL_SECONDS = 30 * 60

    # Socket.IO is intended for clients on the local SoraLink network.
    SOCKETIO_ASYNC_MODE = "threading"


class TestConfig(Config):
    """Configuration for automated tests."""

    TESTING = True
    DEBUG = False
    DATABASE_PATH = Path(
        os.environ.get(
            "SORALINK_TEST_DB_PATH",
            str(BASE_DIR / "data" / "soralink-test.db"),
        )
    )


class ProductionConfig(Config):
    """Configuration for deployment outside local development."""

    ENV = "production"
    DEBUG = False


CONFIG_BY_NAME = {
    "development": Config,
    "test": TestConfig,
    "testing": TestConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None) -> type[Config]:
    """Return the selected configuration class."""
    selected = (name or os.environ.get("SORALINK_ENV", "development"))
    selected = selected.strip().lower()

    try:
        return CONFIG_BY_NAME[selected]
    except KeyError as exc:
        raise ValueError(
            f"Unknown SoraLink environment: {selected}"
        ) from exc
