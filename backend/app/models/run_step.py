import enum
from sqlalchemy import String, Integer, ForeignKey, JSON, Enum as SAEnum, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class StepStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    passed = "passed"
    failed = "failed"


class RunStep(Base):
    __tablename__ = "run_steps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    input_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    screenshot_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[StepStatus] = mapped_column(
        SAEnum(StepStatus), nullable=False, default=StepStatus.pending
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # relationships
    run: Mapped["Run"] = relationship(back_populates="steps")

    __table_args__ = (
        Index("ix_run_steps_run_id_step_index", "run_id", "step_index"),
    )

    def __repr__(self) -> str:
        return f"<RunStep(id={self.id}, action={self.action!r})>"
