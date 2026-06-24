"""Unit tests for app.engine.self_heal.

The three-layer fallback (rule → LLM → vision) is verified by stubbing the
individual layer methods, so we test the orchestration logic without a browser
or LLM. Pure parsing/cost helpers are tested directly.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.engine import self_heal as sh
from app.engine.self_heal import (
    SelfHealEngine,
    HealResult,
    _extract_selector_from_llm_response,
    _build_heal_prompt,
    _estimate_cost,
)
from app.engine.models import StepContext
from app.engine.self_heal import _parse_vision_coords
from app.llm.schemas import Usage, ChatResult


def _ctx() -> StepContext:
    return StepContext(run_id=1, step_index=0, action="click",
                       params={"selector": "#x"}, base_url="https://e.com")


# ── try_heal: layering ──

class TestTryHealLayering:
    @pytest.mark.asyncio
    async def test_disabled_returns_none(self, monkeypatch):
        monkeypatch.setattr(sh.settings, "self_heal_enabled", False)
        engine = SelfHealEngine(db=MagicMock())
        assert await engine.try_heal(MagicMock(), "#x", _ctx()) is None

    @pytest.mark.asyncio
    async def test_rule_layer_short_circuits(self, monkeypatch):
        monkeypatch.setattr(sh.settings, "self_heal_enabled", True)
        engine = SelfHealEngine(db=MagicMock())
        engine._rule_heal = AsyncMock(return_value="#fixed")
        engine._llm_heal = AsyncMock()

        result = await engine.try_heal(MagicMock(), "#x", _ctx())
        assert result == HealResult(healed_selector="#fixed", method="rule")
        engine._llm_heal.assert_not_awaited()  # rule succeeded → no LLM call

    @pytest.mark.asyncio
    async def test_falls_back_to_llm(self, monkeypatch):
        monkeypatch.setattr(sh.settings, "self_heal_enabled", True)
        engine = SelfHealEngine(db=MagicMock())
        engine._rule_heal = AsyncMock(return_value=None)
        engine._llm_heal = AsyncMock(return_value=("#llm", 0.0012))

        result = await engine.try_heal(MagicMock(), "#x", _ctx())
        assert result.method == "llm"
        assert result.healed_selector == "#llm"
        assert result.llm_cost == 0.0012

    @pytest.mark.asyncio
    async def test_no_db_skips_llm_layer(self, monkeypatch):
        monkeypatch.setattr(sh.settings, "self_heal_enabled", True)
        engine = SelfHealEngine(db=None)
        engine._rule_heal = AsyncMock(return_value=None)
        assert await engine.try_heal(MagicMock(), "#x", _ctx()) is None

    @pytest.mark.asyncio
    async def test_falls_back_to_vision(self, monkeypatch):
        monkeypatch.setattr(sh.settings, "self_heal_enabled", True)
        engine = SelfHealEngine(db=MagicMock())
        engine._rule_heal = AsyncMock(return_value=None)
        engine._llm_heal = AsyncMock(return_value=(None, None))
        engine._vision_heal = AsyncMock(return_value=("#vis", 0.0003))

        result = await engine.try_heal(MagicMock(), "#x", _ctx())
        assert result.method == "vision"
        assert result.healed_selector == "#vis"
        assert result.llm_cost == 0.0003

    @pytest.mark.asyncio
    async def test_all_layers_fail(self, monkeypatch):
        monkeypatch.setattr(sh.settings, "self_heal_enabled", True)
        engine = SelfHealEngine(db=MagicMock())
        engine._rule_heal = AsyncMock(return_value=None)
        engine._llm_heal = AsyncMock(return_value=(None, None))
        engine._vision_heal = AsyncMock(return_value=(None, None))
        assert await engine.try_heal(MagicMock(), "#x", _ctx()) is None


class TestVisionHeal:
    @pytest.mark.asyncio
    async def test_returns_selector_from_coords(self, monkeypatch):
        engine = SelfHealEngine(db=MagicMock())
        page = MagicMock()
        page.screenshot = AsyncMock(return_value=b"\x89PNG")
        page.evaluate = AsyncMock(return_value="#target")  # elementFromPoint result

        provider = MagicMock()
        provider.vision = AsyncMock(return_value=ChatResult(
            content='{"found": true, "x": 120, "y": 240}',
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            model="m",
        ))
        monkeypatch.setattr(sh, "get_provider", lambda cfg: provider)
        monkeypatch.setattr(sh, "_load_default_llm_config", AsyncMock(return_value=MagicMock()))
        monkeypatch.setattr(sh, "_selector_works", AsyncMock(return_value=True))

        healed, cost = await engine._vision_heal(page, "#broken", _ctx())
        assert healed == "#target"
        assert cost is not None
        page.evaluate.assert_awaited()  # mapped coords back to a DOM node

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self, monkeypatch):
        engine = SelfHealEngine(db=MagicMock())
        page = MagicMock()
        page.screenshot = AsyncMock(return_value=b"\x89PNG")
        page.evaluate = AsyncMock()

        provider = MagicMock()
        provider.vision = AsyncMock(return_value=ChatResult(
            content='{"found": false}', usage=Usage(), model="m"))
        monkeypatch.setattr(sh, "get_provider", lambda cfg: provider)
        monkeypatch.setattr(sh, "_load_default_llm_config", AsyncMock(return_value=MagicMock()))

        healed, cost = await engine._vision_heal(page, "#broken", _ctx())
        assert healed is None and cost is None
        page.evaluate.assert_not_awaited()  # no coords → no DOM mapping


class TestParseVisionCoords:
    def test_plain(self):
        assert _parse_vision_coords('{"found": true, "x": 10, "y": 20}') == (10, 20)

    def test_fenced(self):
        assert _parse_vision_coords('```json\n{"found": true, "x": 5, "y": 6}\n```') == (5, 6)

    def test_not_found(self):
        assert _parse_vision_coords('{"found": false}') is None

    def test_garbage(self):
        assert _parse_vision_coords("no json") is None


# ── pure helpers ──

class TestExtractSelectorFromLlm:
    def test_plain_json(self):
        assert _extract_selector_from_llm_response('{"selector": "#a"}') == "#a"

    def test_fenced_json(self):
        text = '```json\n{"selector": "button.ok", "confidence": 0.9}\n```'
        assert _extract_selector_from_llm_response(text) == "button.ok"

    def test_json_with_surrounding_text(self):
        text = 'Here you go: {"selector": "#submit"} done'
        assert _extract_selector_from_llm_response(text) == "#submit"

    def test_null_selector_returns_none(self):
        assert _extract_selector_from_llm_response('{"selector": null}') is None

    def test_garbage_returns_none(self):
        assert _extract_selector_from_llm_response("no json here") is None


class TestBuildHealPrompt:
    def test_includes_selector_and_elements(self):
        prompt = _build_heal_prompt(
            "#broken",
            {"tag": "button", "text": "Save"},
            [{"tag": "button", "text": "Save", "selector": "button.save"}],
        )
        assert "#broken" in prompt
        assert "button.save" in prompt


class TestEstimateCost:
    def test_none_usage(self):
        assert _estimate_cost(None) is None

    def test_zero_tokens(self):
        assert _estimate_cost(Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0)) is None

    def test_positive_tokens(self):
        cost = _estimate_cost(Usage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500))
        assert cost is not None and cost > 0
