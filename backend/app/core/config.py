import secrets
import warnings
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "webbot"
    debug: bool = True

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/webbot.db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Security
    secret_key: str = ""
    fernet_key: str = ""  # auto-derived from secret_key if empty

    # CORS — comma-separated list of allowed frontend origins.
    # Defaults to the local Vite dev server; override via CORS_ORIGINS in prod.
    # Use "*" to allow any origin (credentials are auto-disabled in that case).
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Playwright
    headless: bool = True

    # Self-heal
    self_heal_enabled: bool = True
    self_heal_max_attempts: int = 1

    # Total wall-clock budget for a single run (all steps). A run exceeding this
    # is marked failed so a hung page can't occupy the browser indefinitely.
    run_timeout_seconds: int = 300

    def model_post_init(self, __context):
        if not self.secret_key:
            if self.debug:
                self.secret_key = secrets.token_hex(32)
                warnings.warn(
                    "SECRET_KEY not set; a random key has been generated for this session. "
                    "Set SECRET_KEY in your .env file to persist sessions across restarts.",
                    stacklevel=2,
                )
            else:
                raise RuntimeError(
                    "SECRET_KEY must be set in production. "
                    "Add it to your .env file or environment variables."
                )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def cors_allow_credentials(self) -> bool:
        # The CORS spec forbids credentials together with a "*" origin, and
        # browsers reject such responses. Disable credentials when wildcard.
        return "*" not in self.cors_origins_list

    def get_fernet_key(self) -> str:
        if self.fernet_key:
            return self.fernet_key
        import base64, hashlib
        key = base64.urlsafe_b64encode(
            hashlib.sha256(self.secret_key.encode()).digest()
        )
        return key.decode()


settings = Settings()
