"""Pydantic request/response models and the SSE event envelope.

Every event the agent yields is one of the `type` values below. The frontend
switches on that field to pick a card colour and layout, so the set is a
contract between agent.py and TraceTimeline.jsx — change it in both places.
"""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

EventType = Literal[
    "thinking",      # model emitted reasoning text before deciding
    "tool_call",     # model chose a tool, with arguments
    "tool_result",   # tool returned (or raised), with wall-clock duration
    "answer",        # final answer, with citations
    "done",          # stream terminator: step count + elapsed
    "error",         # unrecoverable failure
]


class Citation(BaseModel):
    filename: str
    page: int


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)


class UploadResponse(BaseModel):
    doc_id: str
    filename: str
    num_pages: int
    num_chunks: int


class DocumentInfo(BaseModel):
    doc_id: str
    filename: str
    num_pages: int
    num_chunks: int
    uploaded_at: str


class HealthResponse(BaseModel):
    status: str
    doc_count: int
    model: str


class Event(BaseModel):
    """One frame on the wire. Extra keys vary by type; unset keys are dropped."""

    type: EventType
    # thinking / answer / error
    content: str | None = None
    message: str | None = None
    # tool_call / tool_result
    call_id: str | None = None
    tool: str | None = None
    args: dict[str, Any] | None = None
    result: Any | None = None
    duration_ms: int | None = None
    # answer
    citations: list[Citation] | None = None
    # done
    steps: int | None = None
    elapsed_ms: int | None = None
    truncated: bool | None = None

    def to_sse(self) -> str:
        """Serialise to a `data: {json}\\n\\n` frame.

        Newlines inside the JSON would split the frame, so we force compact
        separators and let json escape any literal newlines in the payload.
        """
        payload = self.model_dump(exclude_none=True)
        return "data: " + json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n\n"
