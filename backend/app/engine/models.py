from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from app.models.run_step import StepStatus


@dataclass
class StepContext:
    run_id: int
    step_index: int
    action: str
    params: dict
    base_url: str


@dataclass
class StepResult:
    step_index: int
    action: str
    status: StepStatus
    duration_ms: int
    input_json: dict | None
    output_json: dict | None
    screenshot_path: str | None
    error: str | None = None


@dataclass
class WsMessage:
    event: str
    run_id: int
    step_index: int | None
    status: str
    screenshot_url: str | None = None
    error: str | None = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    # ── step detail enrichments (step_update / step_end) ──
    action: str | None = None
    params_summary: str | None = None
    duration_ms: int | None = None
    screenshot_before: str | None = None
    screenshot_after: str | None = None
    dom_snippet: str | None = None
    target_bbox: dict | None = None
    console_logs: list[dict] | None = None
    network_requests: list[dict] | None = None
    # ── heal notice ──
    healed: bool | None = None
    healed_selector: str | None = None
    original_selector: str | None = None

    def to_dict(self) -> dict:
        d = {
            "event": self.event,
            "run_id": self.run_id,
            "step_index": self.step_index,
            "status": self.status,
            "screenshot_url": self.screenshot_url,
            "error": self.error,
            "timestamp": self.timestamp,
        }
        if self.action is not None:
            d["action"] = self.action
        if self.params_summary is not None:
            d["params_summary"] = self.params_summary
        if self.duration_ms is not None:
            d["duration_ms"] = self.duration_ms
        if self.screenshot_before is not None:
            d["screenshot_before"] = self.screenshot_before
        if self.screenshot_after is not None:
            d["screenshot_after"] = self.screenshot_after
        if self.dom_snippet is not None:
            d["dom_snippet"] = self.dom_snippet
        if self.target_bbox is not None:
            d["target_bbox"] = self.target_bbox
        if self.console_logs is not None:
            d["console_logs"] = self.console_logs
        if self.network_requests is not None:
            d["network_requests"] = self.network_requests
        if self.healed is not None:
            d["healed"] = self.healed
        if self.healed_selector is not None:
            d["healed_selector"] = self.healed_selector
        if self.original_selector is not None:
            d["original_selector"] = self.original_selector
        return d
