"""Shared fixtures for engine/LLM unit tests.

All fixtures here are offline: an in-memory SQLite DB and plain Python mocks.
No real browser is launched and no real LLM/HTTP request is made.
"""
from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)
from sqlalchemy.pool import StaticPool

from app.core.database import Base
import app.models  # noqa: F401 — register all models on Base.metadata
from app.models.project import Project
from app.models.test_case import TestCase


@pytest_asyncio.fixture
async def db_session():
    """A throwaway in-memory async DB session with all tables created."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def make_case(db_session):
    """Factory: persist a TestCase (with its Project relationship set in memory)."""
    async def _make(steps, *, self_heal: str = "on", base_url: str = "https://example.com") -> TestCase:
        project = Project(name="demo", base_url=base_url)
        # Assigning project= populates the relationship in the identity map so
        # case.project does not trigger an (async-unsafe) lazy load later.
        case = TestCase(name="case", steps_json=steps, self_heal=self_heal, project=project)
        db_session.add(project)
        db_session.add(case)
        await db_session.flush()
        return case

    return _make
