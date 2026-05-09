from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Screenshot(Base):
    __tablename__ = "screenshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # relationships
    run: Mapped["Run"] = relationship()

    def __repr__(self) -> str:
        return f"<Screenshot(id={self.id}, path={self.path!r})>"
