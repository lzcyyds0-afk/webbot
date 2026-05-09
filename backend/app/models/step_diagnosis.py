from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, JSON, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class StepDiagnosis(Base):
    __tablename__ = "step_diagnosis"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)

    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # relationships
    run: Mapped["Run"] = relationship(back_populates="diagnoses")

    __table_args__ = (
        Index("ix_step_diagnosis_run_id_step_index", "run_id", "step_index", unique=True),
    )

    def __repr__(self) -> str:
        return f"<StepDiagnosis(run_id={self.run_id}, step_index={self.step_index})>"
