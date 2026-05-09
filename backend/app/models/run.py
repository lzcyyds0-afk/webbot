import enum
from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, Enum as SAEnum, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class RunStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    passed = "passed"
    failed = "failed"


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    test_case_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[RunStatus] = mapped_column(
        SAEnum(RunStatus), nullable=False, default=RunStatus.pending, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    narrative: Mapped[str | None] = mapped_column(nullable=True)
    narrative_generated_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # relationships
    test_case: Mapped["TestCase"] = relationship(back_populates="runs")
    steps: Mapped[list["RunStep"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    diagnoses: Mapped[list["StepDiagnosis"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Run(id={self.id}, status={self.status.value})>"
