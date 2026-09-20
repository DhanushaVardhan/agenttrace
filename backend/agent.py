"""The agent loop: plan, call tools, observe, repeat -- emitting every step.

This is the part that makes the project not-a-RAG-chatbot. A single-shot RAG
pipeline retrieves once and answers once. Here the model gets tools and a
budget, and decides for itself whether to search again with different wording,
chain a calculation onto a retrieved number, or stop and answer.

Two invariants:
  * The loop is bounded. MAX_STEPS caps it, and hitting the cap returns a
    partial answer flagged truncated rather than an error. An unbounded agent
    loop is a runaway cost incident waiting to happen.
  * A tool failure never kills the run. The error string goes back to the
    model as the function response so it can correct its arguments or explain.
"""
from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import AsyncGenerator
from typing import Any

from . import config, llm, tools
from .models import Citation, Event
from .store import STORE

log = logging.getLogger("agenttrace.agent")

SYSTEM_PROMPT = """You are a compliance research assistant. You answer questions strictly from a corpus of indexed regulatory and policy PDFs.

Rules, in order of importance:

1. ALWAYS call search_documents before answering anything about the documents. Never answer from prior knowledge about what a regulation says, even when you are confident. Your training data is not the corpus the user uploaded.
2. If the first search returns nothing useful, SEARCH AGAIN with different wording. Try the regulator's own vocabulary, a synonym, or a narrower phrase. Two or three searches with different phrasings is normal and expected.
3. Cite every factual claim inline as [filename, p.N], using the exact filename and page_num from the search results. A sentence stating a fact from the documents must carry a citation.
4. Use the calculate tool for ALL arithmetic, including simple multiplication. Do not compute in your head.
5. If the documents do not contain the answer, say so plainly: "The indexed documents do not cover this." Do not fill the gap from general knowledge. Guessing is worse than an unhelpful answer in a compliance setting.
6. Before each tool call, state in one short sentence what you are looking for and why. These notes are shown to the user as the reasoning trace, so keep them concrete.
7. When you have enough information, stop calling tools and write the final answer. Be direct and specific; quote exact thresholds, dates and defined terms."""

# [rbi_kyc.pdf, p.14] / [rbi_kyc.pdf p. 14] / [rbi_kyc.pdf,p14]
_CITATION_RE = re.compile(r"\[\s*([^\[\],]+?)\s*,?\s*p\.?\s*(\d+)\s*\]", re.IGNORECASE)

# session_id -> clean user/model turns. Deliberately in-memory and lost on
# restart: persisting chat history is out of scope.
_SESSIONS: dict[str, list[dict[str, Any]]] = {}
_MAX_HISTORY_TURNS = 12


def reset_session(session_id: str) -> None:
    _SESSIONS.pop(session_id, None)


def _history(session_id: str) -> list[dict[str, Any]]:
    return _SESSIONS.setdefault(session_id, [])


def _remember(session_id: str, role: str, text: str) -> None:
    """Store only clean user/model text turns.

    Intermediate functionCall/functionResponse pairs are dropped from history
    on purpose: they have to stay exactly paired or the provider rejects the
    conversation, and trimming a window can split a pair. The final answer
    carries the useful context forward anyway.
    """
    turns = _history(session_id)
    turns.append({"role": role, "parts": [{"text": text}]})
    if len(turns) > _MAX_HISTORY_TURNS:
        del turns[: len(turns) - _MAX_HISTORY_TURNS]


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def extract_citations(text: str) -> list[Citation]:
    """Pull [filename, p.N] markers out of the answer, de-duplicated in order.

    Only markers whose filename matches an indexed document survive, so a
    fabricated filename never renders as a clickable source.
    """
    known = {d.filename.lower(): d.filename for d in STORE.documents()}
    seen: set[tuple[str, int]] = set()
    citations: list[Citation] = []

    for raw_name, raw_page in _CITATION_RE.findall(text or ""):
        name = raw_name.strip().strip("'\"")
        page = int(raw_page)
        canonical = known.get(name.lower())
        if canonical is None:
            # tolerate a stem without the .pdf extension
            for lower, original in known.items():
                if lower.rsplit(".", 1)[0] == name.lower():
                    canonical = original
                    break
        if canonical is None or (canonical, page) in seen:
            continue
        seen.add((canonical, page))
        citations.append(Citation(filename=canonical, page=page))

    return citations


def _ui_preview(name: str, result: Any) -> Any:
    """What the trace card shows. The model still receives the full payload.

    Streaming whole chunks to the browser would make the timeline unreadable
    and the frames large, so results are summarised for display only.
    """
    limit = config.TOOL_RESULT_CHAR_LIMIT
    if name == "search_documents" and isinstance(result, list):
        return {
            "hits": len(result),
            "top_score": result[0]["score"] if result else None,
            "preview": [
                {
                    "filename": hit["filename"],
                    "page_num": hit["page_num"],
                    "score": hit["score"],
                    "snippet": hit["text"][:220] + ("..." if len(hit["text"]) > 220 else ""),
                }
                for hit in result[:5]
            ],
        }
    if name == "calculate":
        return {"value": result}
    if isinstance(result, str):
        return {"chars": len(result), "preview": result[:limit]}
    text = json.dumps(result, default=str)
    return {"preview": text[:limit]}


def _model_payload(name: str, result: Any) -> dict[str, Any]:
    """Gemini requires functionResponse.response to be a JSON object."""
    if name == "search_documents":
        return {"results": result}
    if name == "summarize_section":
        return {"summary": result}
    if name == "calculate":
        return {"result": result}
    return {"result": result}


def _parts_for_history(response: llm.LLMResponse) -> list[dict[str, Any]]:
    """Echo the model turn back verbatim.

    Deliberately the raw parts rather than a reconstruction. Reasoning models
    attach a `thoughtSignature` to their functionCall parts and expect it back
    on the next turn; rebuilding the part from just {name, args} drops that
    signature along with the call's own `id`, which degrades or breaks
    multi-step tool use. Passing through exactly what arrived cannot go stale
    as providers add fields.
    """
    return response.raw_parts or [{"text": ""}]


# --------------------------------------------------------------------------
# the loop
# --------------------------------------------------------------------------


async def run_agent(session_id: str, user_message: str) -> AsyncGenerator[Event, None]:
    """Yield one Event per observable step until the agent answers or runs out."""
    started = time.perf_counter()
    contents: list[dict[str, Any]] = list(_history(session_id))
    contents.append({"role": "user", "parts": [{"text": user_message}]})

    steps_used = 0

    try:
        for step in range(config.MAX_STEPS):
            steps_used = step + 1

            response = await llm.generate(
                contents=contents,
                tools=tools.TOOL_SCHEMAS,
                system_instruction=SYSTEM_PROMPT,
            )

            # Reasoning text that accompanies a tool call is the "thinking" card.
            if response.text and response.has_function_call:
                yield Event(type="thinking", content=response.text)

            # No tool call means the model is done deliberating.
            if not response.has_function_call:
                answer = response.text or "I could not produce an answer for that."
                _remember(session_id, "user", user_message)
                _remember(session_id, "model", answer)
                yield Event(
                    type="answer",
                    content=answer,
                    citations=extract_citations(answer),
                )
                yield Event(
                    type="done",
                    steps=steps_used,
                    elapsed_ms=int((time.perf_counter() - started) * 1000),
                    truncated=False,
                )
                return

            contents.append({"role": "model", "parts": _parts_for_history(response)})

            # Gemini may return several calls in one turn; run them in order and
            # send every response back in a single user turn.
            response_parts: list[dict[str, Any]] = []
            for call in response.function_calls:
                yield Event(
                    type="tool_call",
                    call_id=call.call_id,
                    tool=call.name,
                    args=call.args,
                )

                t0 = time.perf_counter()
                try:
                    result = await tools.dispatch(call.name, call.args)
                    payload = _model_payload(call.name, result)
                    preview = _ui_preview(call.name, result)
                except tools.ToolError as exc:
                    payload = {"error": str(exc)}
                    preview = {"error": str(exc)}
                except Exception as exc:  # noqa: BLE001
                    log.exception("unexpected failure in %s", call.name)
                    payload = {"error": f"internal error: {exc}"}
                    preview = {"error": f"internal error: {exc}"}
                duration_ms = int((time.perf_counter() - t0) * 1000)

                yield Event(
                    type="tool_result",
                    call_id=call.call_id,
                    tool=call.name,
                    result=preview,
                    duration_ms=duration_ms,
                )

                function_response: dict[str, Any] = {
                    "name": call.name,
                    "response": payload,
                }
                # Models that issue call ids match the response back by id.
                if call.provider_id:
                    function_response["id"] = call.provider_id
                response_parts.append({"functionResponse": function_response})

            contents.append({"role": "user", "parts": response_parts})

        # --- step budget exhausted ---------------------------------------
        partial = await _forced_answer(contents)
        _remember(session_id, "user", user_message)
        _remember(session_id, "model", partial)
        yield Event(type="answer", content=partial, citations=extract_citations(partial))
        yield Event(
            type="done",
            steps=config.MAX_STEPS,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            truncated=True,
        )

    except llm.LLMError as exc:
        log.warning("llm failure: %s", exc)
        yield Event(type="error", message=str(exc))
        yield Event(
            type="done",
            steps=steps_used,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            truncated=True,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("agent run failed")
        yield Event(type="error", message=f"Agent failed: {exc}")
        yield Event(
            type="done",
            steps=steps_used,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            truncated=True,
        )


async def _forced_answer(contents: list[dict[str, Any]]) -> str:
    """Hitting the step cap should still produce something useful.

    One final call with no tools attached, so the model has to write prose
    from what it already gathered instead of reaching for another search.
    """
    nudge_text = (
        "You have reached the tool-call limit. Answer now using only what you have "
        "already retrieved. Keep the [filename, p.N] citations, and state plainly "
        "which part of the question you could not resolve."
    )

    # The last turn is the functionResponse turn, which also has role "user".
    # Appending a second user turn would leave two in a row, so the nudge is
    # merged into that turn instead.
    final = [dict(turn) for turn in contents]
    if final and final[-1].get("role") == "user":
        final[-1]["parts"] = [*final[-1]["parts"], {"text": nudge_text}]
    else:
        final.append({"role": "user", "parts": [{"text": nudge_text}]})

    try:
        response = await llm.generate(
            contents=final,
            system_instruction=SYSTEM_PROMPT,
            temperature=0.1,
        )
        if response.text:
            return f"{response.text}\n\n_(Stopped at the {config.MAX_STEPS}-step limit.)_"
    except llm.LLMError as exc:
        log.warning("forced answer failed: %s", exc)
    return (
        f"I hit the {config.MAX_STEPS}-step limit before reaching a confident answer. "
        "Try narrowing the question, or ask about one document at a time."
    )
