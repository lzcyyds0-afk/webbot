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

    # Playwright
    headless: bool = True

    # Self-heal
    self_heal_enabled: bool = True
    self_heal_max_attempts: int = 1

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

    def get_fernet_key(self) -> str:
        if self.fernet_key:
            return self.fernet_key
        import base64, hashlib
        key = base64.urlsafe_b64encode(
            hashlib.sha256(self.secret_key.encode()).digest()
        )
        return key.decode()


settings = Settings()
