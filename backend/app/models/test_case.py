from sqlalchemy import String, Integer, ForeignKey, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import TimestampMixin


class TestCase(TimestampMixin, Base):
    __tablename__ = "test_cases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    steps_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)
    cookies_json: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    # Optional auth bundle:
    # {
    #   "local_storage": {key: value, ...},     # localStorage entries
    #   "session_storage": {key: value, ...},   # sessionStorage entries
    #   "credentials": {                        # encrypted username/password fallback
    #     "url": "...", "username": "...", "password_encrypted": "...",
    #     "username_selector": "...", "password_selector": "...",
    #     "submit_selector": "...", "success_url_pattern": "..."
    #   }
    # }
    auth_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    self_heal: Mapped[str] = mapped_column(String(16), nullable=False, default="on")

    # relationships
    project: Mapped["Project"] = relationship(back_populates="test_cases")
    runs: Mapped[list["Run"]] = relationship(
        back_populates="test_case", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<TestCase(id={self.id}, name={self.name!r})>"
