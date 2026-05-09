from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, Float, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class HealEvent(Base):
    __tablename__ = "heal_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    original_selector: Mapped[str] = mapped_column(String(512), nullable=False)
    healed_selector: Mapped[str] = mapped_column(String(512), nullable=False)
    method: Mapped[str] = mapped_column(String(32), nullable=False)  # "rule" | "llm" | "vision"
    llm_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("ix_heal_events_run_id_step_index", "run_id", "step_index"),
    )

    def __repr__(self) -> str:
        return f"<HealEvent(run_id={self.run_id}, step={self.step_index}, method={self.method!r})>"
