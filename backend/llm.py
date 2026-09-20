"""Thin async wrapper over the Gemini REST API.

Deliberately not the google-generativeai SDK: the whole provider surface this
project needs is two endpoints, and keeping it as raw HTTP means swapping in
OpenAI or Anthropic is a change to this one file. It also keeps the container
small, which matters on a free tier.

Endpoints used:
  POST {base}/models/{model}:generateContent        - chat + function calling
  POST {base}/models/{embed}:batchEmbedContents     - up to 100 texts per call
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from . import config

log = logging.getLogger("agenttrace.llm")

_RETRY_STATUSES = {429, 500, 502, 503, 504}
_MAX_RETRIES = 4
_TIMEOUT = httpx.Timeout(60.0, connect=15.0)


class LLMError(RuntimeError):
    """Raised when the provider fails in a way we cannot retry past."""


@dataclass
class FunctionCall:
    name: str
    args: dict[str, Any]
    call_id: str


@dataclass
class LLMResponse:
    """Flattened view of one candidate's parts."""

    text: str = ""
    function_calls: list[FunctionCall] = field(default_factory=list)
    finish_reason: str = ""
    raw_parts: list[dict[str, Any]] = field(default_factory=list)

    @property
    def has_function_call(self) -> bool:
        return bool(self.function_calls)


# --------------------------------------------------------------------------
# transport
# --------------------------------------------------------------------------

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """One connection pool for the process, created lazily."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=_TIMEOUT)
    return _client


async def aclose() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


async def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST with exponential backoff on the retryable status codes.

    Rate limiting is the single most likely failure on Gemini's free tier, so
    it gets real handling rather than a bare raise_for_status().
    """
    url = f"{config.GEMINI_BASE_URL}/{path}"
    headers = {
        "x-goog-api-key": config.require_api_key(),
        "Content-Type": "application/json",
    }
    client = _get_client()
    delay = 1.0
    last_detail = ""

    for attempt in range(_MAX_RETRIES):
        try:
            resp = await client.post(url, json=payload, headers=headers)
        except httpx.RequestError as exc:
            last_detail = f"network error: {exc}"
            log.warning("gemini request failed (attempt %d): %s", attempt + 1, exc)
        else:
            if resp.status_code == 200:
                return resp.json()
            last_detail = f"HTTP {resp.status_code}: {resp.text[:300]}"
            if resp.status_code not in _RETRY_STATUSES:
                # 400/403/404 will not get better by trying again.
                raise LLMError(last_detail)
            log.warning("gemini %s (attempt %d)", last_detail, attempt + 1)

        if attempt < _MAX_RETRIES - 1:
            await asyncio.sleep(delay)
            delay *= 2

    raise LLMError(f"Gemini request failed after {_MAX_RETRIES} attempts. {last_detail}")


# --------------------------------------------------------------------------
# generation
# --------------------------------------------------------------------------


async def generate(
    contents: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    system_instruction: str | None = None,
    temperature: float = 0.2,
) -> LLMResponse:
    """One turn of the conversation.

    `contents` is Gemini's message list. A model turn carries `functionCall`
    parts; the matching tool output goes back as a `functionResponse` part on
    a turn with role "user".
    """
    payload: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {"temperature": temperature, "maxOutputTokens": 2048},
    }
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
    if tools:
        payload["tools"] = [{"functionDeclarations": tools}]

    data = await _post(f"models/{config.GEMINI_MODEL}:generateContent", payload)

    candidates = data.get("candidates") or []
    if not candidates:
        # Usually a safety block; surface the reason rather than an empty answer.
        reason = (data.get("promptFeedback") or {}).get("blockReason", "unknown")
        raise LLMError(f"Gemini returned no candidates (blockReason={reason}).")

    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []

    text_fragments: list[str] = []
    calls: list[FunctionCall] = []
    for idx, part in enumerate(parts):
        if "text" in part and part["text"]:
            text_fragments.append(part["text"])
        fc = part.get("functionCall")
        if fc:
            calls.append(
                FunctionCall(
                    name=fc.get("name", ""),
                    args=dict(fc.get("args") or {}),
                    # Gemini does not issue tool-call ids, so we mint a stable
                    # one per turn for the UI to pair call with result.
                    call_id=f"c{len(calls) + 1}_{idx}",
                )
            )

    return LLMResponse(
        text="".join(text_fragments).strip(),
        function_calls=calls,
        finish_reason=candidate.get("finishReason", ""),
        raw_parts=parts,
    )


# --------------------------------------------------------------------------
# embeddings
# --------------------------------------------------------------------------


async def embed_texts(
    texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT"
) -> list[list[float]]:
    """Batch-embed. `task_type` must be RETRIEVAL_QUERY for search queries.

    Gemini's retrieval embeddings are asymmetric: documents and queries are
    projected differently, and mixing the task types measurably degrades recall.
    """
    if not texts:
        return []

    model_path = f"models/{config.EMBED_MODEL}"
    out: list[list[float]] = []

    for start in range(0, len(texts), config.EMBED_BATCH_SIZE):
        batch = texts[start : start + config.EMBED_BATCH_SIZE]
        payload = {
            "requests": [
                {
                    "model": model_path,
                    "content": {"parts": [{"text": t}]},
                    "taskType": task_type,
                }
                for t in batch
            ]
        }
        data = await _post(f"{model_path}:batchEmbedContents", payload)
        embeddings = data.get("embeddings") or []
        if len(embeddings) != len(batch):
            raise LLMError(
                f"Embedding count mismatch: asked for {len(batch)}, got {len(embeddings)}."
            )
        out.extend(e["values"] for e in embeddings)

    return out


async def embed_query(text: str) -> list[float]:
    vectors = await embed_texts([text], task_type="RETRIEVAL_QUERY")
    return vectors[0]
