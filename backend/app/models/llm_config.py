from sqlalchemy import String, Boolean, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.models.base import TimestampMixin


class LLMConfig(TimestampMixin, Base):
    __tablename__ = "llm_configs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(String(512), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    params_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    def get_plain_key(self) -> str:
        from app.core.security import decrypt_value
        return decrypt_value(self.api_key_encrypted)

    def set_plain_key(self, plain: str) -> None:
        from app.core.security import encrypt_value
        self.api_key_encrypted = encrypt_value(plain)

    def __repr__(self) -> str:
        return f"<LLMConfig(id={self.id}, name={self.name!r}, provider={self.provider!r})>"
