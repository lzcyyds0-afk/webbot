"""Tests for app.llm.visual — Visual Analyzer.

We test the parsing and annotation logic without making real LLM calls.
The analyze() function itself is tested by mocking the provider.vision().
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.visual import (
    VisualResult,
    BBox,
    _parse_json_response,
    _build_visual_result,
    _degraded_result,
    _draw_annotated,
    analyze,
)
from app.llm.schemas import Message, ChatResult, ImageRef, Usage

FIXTURES = Path(__file__).parent / "fixtures" / "visual"


# ──────────────────────────────────────────────
#  Fixtures
# ──────────────────────────────────────────────

@pytest.fixture
def screenshot_pass() -> str:
    return str(FIXTURES / "coze_pass.png")

@pytest.fixture
def screenshot_partial() -> str:
    return str(FIXTURES / "coze_partial.png")

@pytest.fixture
def screenshot_fail() -> str:
    return str(FIXTURES / "coze_fail.png")


# ──────────────────────────────────────────────
#  Unit tests: JSON parsing
# ──────────────────────────────────────────────

class TestParseJsonResponse:
    def test_clean_json(self):
        text = '{"pass": true, "confidence": 0.9, "reason": "ok", "bboxes": []}'
        result = _parse_json_response(text)
        assert result["pass"] is True
        assert result["confidence"] == 0.9

    def test_json_in_markdown_fence(self):
        text = '```json\n{"pass": false, "confidence": 0.8, "reason": "fail", "bboxes": []}\n```'
        result = _parse_json_response(text)
        assert result["pass"] is False

    def test_json_with_extra_text(self):
        text = 'Here is my analysis:\n{"pass": true, "confidence": 0.7, "reason": "looks good", "bboxes": []}\nEnd.'
        result = _parse_json_response(text)
        assert result["pass"] is True

    def test_json_with_bboxes(self):
        text = json.dumps({
            "pass": False,
            "confidence": 0.85,
            "reason": "Missing connection",
            "bboxes": [{"label": "gap", "x": 300, "y": 310, "w": 200, "h": 20}],
        })
        result = _parse_json_response(text)
        assert len(result["bboxes"]) == 1
        assert result["bboxes"][0]["label"] == "gap"

    def test_invalid_json_raises(self):
        from app.llm.visual import _ParseError
        with pytest.raises(_ParseError):
            _parse_json_response("This is not JSON at all, just plain text.")


class TestBuildVisualResult:
    def test_full_result(self):
        data = {
            "pass": True,
            "confidence": 0.95,
            "reason": "All good",
            "bboxes": [{"label": "ok_button", "x": 100, "y": 50, "w": 80, "h": 30}],
        }
        result = _build_visual_result(data)
        assert result.passed is True
        assert result.confidence == 0.95
        assert result.reason == "All good"
        assert len(result.bboxes) == 1
        assert result.bboxes[0].label == "ok_button"

    def test_confidence_clamped(self):
        data = {"pass": True, "confidence": 1.5, "reason": "", "bboxes": []}
        result = _build_visual_result(data)
        assert result.confidence == 1.0

        data2 = {"pass": False, "confidence": -0.1, "reason": "", "bboxes": []}
        result2 = _build_visual_result(data2)
        assert result2.confidence == 0.0

    def test_missing_fields_default(self):
        data = {"pass": True}
        result = _build_visual_result(data)
        assert result.confidence == 0.5
        assert result.reason == ""
        assert result.bboxes == []

    def test_invalid_bbox_skipped(self):
        data = {
            "pass": False,
            "confidence": 0.8,
            "reason": "error",
            "bboxes": [
                {"label": "ok", "x": 10, "y": 10, "w": 50, "h": 50},
                {"label": "bad", "x": "not_a_number"},  # should be skipped
            ],
        }
        result = _build_visual_result(data)
        assert len(result.bboxes) == 1


class TestDegradedResult:
    def test_pass_keyword(self):
        result = _degraded_result("The test seems to pass with no issues.")
        assert result.passed is True
        assert result.confidence == 0.3

    def test_fail_keyword(self):
        result = _degraded_result("The element failed to appear.")
        assert result.passed is False
        assert result.confidence == 0.3

    def test_no_keyword(self):
        result = _degraded_result("Something happened.")
        assert result.passed is False


# ──────────────────────────────────────────────
#  Unit tests: annotated image drawing
# ──────────────────────────────────────────────

class TestDrawAnnotated:
    @pytest.mark.asyncio
    async def test_draw_with_bboxes(self, screenshot_fail):
        bboxes = [
            BBox(label="error_gap", x=300, y=290, w=120, h=40),
            BBox(label="ok_node", x=100, y=200, w=200, h=150),
        ]
        path = await _draw_annotated(
            screenshot_fail, bboxes, run_id=99, step_index=0
        )
        assert path is not None
        assert path.exists()
        assert "99" in str(path)
        assert "0_annot.png" in str(path)

    @pytest.mark.asyncio
    async def test_draw_no_bboxes(self, screenshot_pass):
        path = await _draw_annotated(
            screenshot_pass, [], run_id=1, step_index=0
        )
        assert path is None  # No bboxes -> no annotation needed


# ──────────────────────────────────────────────
#  Integration test: analyze() with mocked provider
# ──────────────────────────────────────────────

class TestAnalyze:
    @pytest.mark.asyncio
    async def test_analyze_pass(self, screenshot_pass):
        """Test analyze() with a passing screenshot (mocked LLM)."""
        mock_chat_result = ChatResult(
            content=json.dumps({
                "pass": True,
                "confidence": 0.92,
                "reason": "Green connection line visible between Start and LLM nodes.",
                "bboxes": [{"label": "ok_connection", "x": 305, "y": 310, "w": 190, "h": 20}],
            }),
            usage=Usage(prompt_tokens=500, completion_tokens=100, total_tokens=600),
            model="gpt-4o",
        )

        mock_provider = AsyncMock()
        mock_provider.vision.return_value = mock_chat_result

        # Mock DB session
        mock_db = AsyncMock()

        with patch("app.llm.visual.get_provider", return_value=mock_provider), \
             patch("app.llm.visual._load_config", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = AsyncMock(provider="openai", model="gpt-4o")

            result = await analyze(
                screenshot_path=screenshot_pass,
                expectation="There should be a green connection line between the two nodes.",
                llm_config_id=1,
                db=mock_db,
                run_id=1,
                step_index=0,
            )

        assert result.passed is True
        assert result.confidence == 0.92
        assert "Green connection" in result.reason
        assert len(result.bboxes) == 1
        assert result.annotated_path is not None

    @pytest.mark.asyncio
    async def test_analyze_fail(self, screenshot_fail):
        """Test analyze() with a failing screenshot (mocked LLM)."""
        mock_chat_result = ChatResult(
            content=json.dumps({
                "pass": False,
                "confidence": 0.88,
                "reason": "No connection line between nodes. Red error indicator present.",
                "bboxes": [{"label": "missing_connection", "x": 300, "y": 290, "w": 120, "h": 40}],
            }),
            usage=Usage(prompt_tokens=500, completion_tokens=100, total_tokens=600),
            model="gpt-4o",
        )

        mock_provider = AsyncMock()
        mock_provider.vision.return_value = mock_chat_result
        mock_db = AsyncMock()

        with patch("app.llm.visual.get_provider", return_value=mock_provider), \
             patch("app.llm.visual._load_config", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = AsyncMock(provider="openai", model="gpt-4o")

            result = await analyze(
                screenshot_path=screenshot_fail,
                expectation="There should be a connection line between Start and LLM nodes.",
                llm_config_id=1,
                db=mock_db,
                run_id=2,
                step_index=0,
            )

        assert result.passed is False
        assert result.confidence == 0.88
        assert "No connection" in result.reason

    @pytest.mark.asyncio
    async def test_analyze_partial(self, screenshot_partial):
        """Test analyze() with a partial pass screenshot (mocked LLM)."""
        mock_chat_result = ChatResult(
            content=json.dumps({
                "pass": False,
                "confidence": 0.75,
                "reason": "Connection exists but is yellow/dashed indicating incomplete configuration.",
                "bboxes": [
                    {"label": "warning_connection", "x": 305, "y": 310, "w": 190, "h": 20},
                    {"label": "warning_badge", "x": 800, "y": 200, "w": 300, "h": 80},
                ],
            }),
            usage=Usage(prompt_tokens=500, completion_tokens=120, total_tokens=620),
            model="gpt-4o",
        )

        mock_provider = AsyncMock()
        mock_provider.vision.return_value = mock_chat_result
        mock_db = AsyncMock()

        with patch("app.llm.visual.get_provider", return_value=mock_provider), \
             patch("app.llm.visual._load_config", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = AsyncMock(provider="openai", model="gpt-4o")

            result = await analyze(
                screenshot_path=screenshot_partial,
                expectation="There should be a solid green connection line between the two nodes.",
                llm_config_id=1,
                db=mock_db,
                run_id=3,
                step_index=0,
            )

        assert result.passed is False
        assert result.confidence == 0.75
        assert len(result.bboxes) == 2

    @pytest.mark.asyncio
    async def test_analyze_parse_retry(self, screenshot_pass):
        """Test that analyze() retries once on parse failure, then degrades."""
        # First call returns garbage, second call returns valid JSON
        bad_result = ChatResult(
            content="I think the screenshot looks good. Pass!",
            usage=Usage(),
            model="gpt-4o",
        )
        good_result = ChatResult(
            content=json.dumps({
                "pass": True,
                "confidence": 0.8,
                "reason": "Looks good on retry.",
                "bboxes": [],
            }),
            usage=Usage(),
            model="gpt-4o",
        )

        mock_provider = AsyncMock()
        mock_provider.vision.side_effect = [bad_result, good_result]
        mock_db = AsyncMock()

        with patch("app.llm.visual.get_provider", return_value=mock_provider), \
             patch("app.llm.visual._load_config", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = AsyncMock(provider="openai", model="gpt-4o")

            result = await analyze(
                screenshot_path=screenshot_pass,
                expectation="Should look good.",
                llm_config_id=1,
                db=mock_db,
            )

        assert result.passed is True
        assert result.confidence == 0.8
        assert mock_provider.vision.call_count == 2
