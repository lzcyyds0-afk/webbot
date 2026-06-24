"""Unit tests for app.engine.runner.Runner orchestration.

The browser, storage, capturer and action executor are all mocked, so no real
page is driven. A real in-memory DB session (from conftest) is used so we can
assert that Run / RunStep / HealEvent rows are actually persisted.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import func, select

from app.engine.runner import Runner
from app.engine.models import StepResult, WsMessage
from app.engine.step_capturer import StepCaptureData
from app.engine.ws_broadcaster import WsBroadcaster
from app.models.run import RunStatus
from app.models.run_step import RunStep, StepStatus
from app.models.heal_event import HealEvent


class RecordingBroadcaster(WsBroadcaster):
    def __init__(self) -> None:
        self.messages: list[WsMessage] = []

    async def emit(self, message: WsMessage) -> None:
        self.messages.append(message)

    def events(self) -> list[str]:
        return [m.event for m in self.messages]


class FakeExecutor:
    """Returns pre-baked StepResults keyed by step index; records calls."""
    def __init__(self, results: list[StepResult]) -> None:
        self._results = results
        self.calls: list = []

    async def execute(self, page, ctx):
        self.calls.append(ctx)
        return self._results[ctx.step_index]


def _result(idx: int, status: StepStatus, output=None) -> StepResult:
    return StepResult(
        step_index=idx,
        action="click",
        status=status,
        duration_ms=5,
        input_json={},
        output_json=output,
        screenshot_path=None,
    )


def _wire(runner: Runner, results: list[StepResult]):
    """Replace the runner's heavy collaborators with mocks. Returns the storage
    mock so tests can assert on screenshot calls."""
    runner._executor = FakeExecutor(results)

    storage = MagicMock()
    storage.screenshot_path = MagicMock(return_value=Path("shot.png"))
    storage.save_screenshot = AsyncMock(return_value="shot.png")
    runner._storage = storage

    capturer = MagicMock()
    capturer.setup = AsyncMock()
    capturer.start_step = MagicMock()
    capturer.capture_target = AsyncMock()
    capturer.end_step = MagicMock()
    capturer.get_data = MagicMock(return_value=StepCaptureData())
    capturer.teardown = AsyncMock()
    runner._capturer = capturer

    return storage


def _fake_browser_patch():
    """Patch the shared-browser accessor. The fake page exposes an awaitable
    context.close() since the runner closes the per-run context (not the browser)."""
    page = MagicMock()
    page.context = MagicMock()
    page.context.close = AsyncMock()
    bm = MagicMock()
    bm.new_page = AsyncMock(return_value=page)
    return patch("app.engine.runner.get_shared_browser", new=AsyncMock(return_value=bm)), bm


class TestRunnerOrchestration:
    @pytest.mark.asyncio
    async def test_all_steps_pass(self, db_session, make_case):
        case = await make_case([
            {"action": "goto", "url": "/"},
            {"action": "click", "selector": "#a"},
        ])
        bcast = RecordingBroadcaster()
        runner = Runner(db=db_session, broadcaster=bcast)
        _wire(runner, [_result(0, StepStatus.passed), _result(1, StepStatus.passed)])

        cm, bm = _fake_browser_patch()
        with cm, patch("app.engine.runner.persist_step_details"):
            run = await runner.run(case)

        assert run.status == RunStatus.passed
        assert runner._executor.calls and len(runner._executor.calls) == 2
        count = await db_session.scalar(
            select(func.count()).select_from(RunStep).where(RunStep.run_id == run.id)
        )
        assert count == 2
        assert bcast.events()[-1] == "run_end"
        # The per-run context is closed; the shared browser is left running.
        bm.new_page.return_value.context.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_time_budget_stops_execution(self, db_session, make_case, monkeypatch):
        import app.engine.runner as runner_mod
        monkeypatch.setattr(runner_mod.settings, "run_timeout_seconds", -1)

        case = await make_case([{"action": "click", "selector": "#a"}])
        runner = Runner(db=db_session, broadcaster=RecordingBroadcaster())
        _wire(runner, [_result(0, StepStatus.passed)])

        cm, _ = _fake_browser_patch()
        with cm, patch("app.engine.runner.persist_step_details"):
            run = await runner.run(case)

        # Budget exhausted before the first step → marked failed, nothing executed.
        assert run.status == RunStatus.failed
        assert len(runner._executor.calls) == 0

    @pytest.mark.asyncio
    async def test_failure_stops_remaining_steps(self, db_session, make_case):
        case = await make_case([
            {"action": "click", "selector": "#a"},
            {"action": "click", "selector": "#b"},
            {"action": "click", "selector": "#c"},
        ])
        runner = Runner(db=db_session, broadcaster=RecordingBroadcaster())
        _wire(runner, [
            _result(0, StepStatus.passed),
            _result(1, StepStatus.failed),
            _result(2, StepStatus.passed),
        ])

        cm, _ = _fake_browser_patch()
        with cm, \
             patch("app.engine.runner.persist_step_details"), \
             patch("app.engine.diagnosis.diagnose_failed_step", new=AsyncMock()):
            run = await runner.run(case)

        assert run.status == RunStatus.failed
        # 3rd step must NOT execute after the 2nd fails
        assert len(runner._executor.calls) == 2

    @pytest.mark.asyncio
    async def test_screenshot_step_passes_full_page(self, db_session, make_case):
        case = await make_case([{"action": "screenshot", "full_page": True}])
        runner = Runner(db=db_session, broadcaster=RecordingBroadcaster())
        storage = _wire(runner, [_result(0, StepStatus.passed)])

        cm, _ = _fake_browser_patch()
        with cm, patch("app.engine.runner.persist_step_details"):
            await runner.run(case)

        # The dedicated screenshot step's after-capture must honor full_page=True.
        full_page_calls = [
            c for c in storage.save_screenshot.await_args_list
            if c.kwargs.get("full_page") is True
        ]
        assert len(full_page_calls) == 1

    @pytest.mark.asyncio
    async def test_heal_event_is_recorded(self, db_session, make_case):
        case = await make_case([{"action": "click", "selector": "#old"}])
        bcast = RecordingBroadcaster()
        runner = Runner(db=db_session, broadcaster=bcast)
        healed_output = {
            "healed": True,
            "healed_selector": "#new",
            "_original_selector": "#old",
            "_heal_method": "rule",
        }
        _wire(runner, [_result(0, StepStatus.passed, output=healed_output)])

        cm, _ = _fake_browser_patch()
        with cm, patch("app.engine.runner.persist_step_details"):
            run = await runner.run(case)

        count = await db_session.scalar(
            select(func.count()).select_from(HealEvent).where(HealEvent.run_id == run.id)
        )
        assert count == 1
        assert "heal_notice" in bcast.events()
