"""Seed script: insert demo data for development.

Usage:
    PYTHONPATH=. uv run python seed.py
"""
import asyncio
from datetime import datetime

from app.core.database import async_session, engine
from app.core.database import Base
from app.models import Project, TestCase, LLMConfig


async def seed() -> None:
    async with async_session() as session:
        # 1) Demo project
        project = Project(
            name="Demo Project",
            base_url="https://example.com",
        )
        session.add(project)
        await session.flush()

        # 2) Demo test case with 3 steps
        test_case = TestCase(
            project_id=project.id,
            name="Homepage smoke test",
            steps_json=[
                {"action": "goto", "url": "/"},
                {"action": "click", "selector": "#login-btn"},
                {"action": "fill", "selector": "#username", "value": "admin"},
            ],
        )
        session.add(test_case)

        # 3) Demo LLM config (encrypted key)
        llm = LLMConfig(
            name="GPT-4o (demo)",
            provider="openai",
            model="gpt-4o",
            api_key_encrypted="placeholder",  # will be set below
            base_url="https://api.openai.com/v1",
            params_json={"temperature": 0.1, "max_tokens": 4096},
            is_default=True,
        )
        llm.set_plain_key("sk-your-api-key-here")
        session.add(llm)

        await session.commit()
        print(f"Seeded project: {project} (id={project.id})")
        print(f"Seeded test_case: {test_case} (id={test_case.id})")
        print(f"Seeded llm_config: {llm} (id={llm.id})")
        print(f"LLM plain key roundtrip: {llm.get_plain_key()!r}")


async def main() -> None:
    # Create tables (for dev without Alembic)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed()


if __name__ == "__main__":
    asyncio.run(main())
