"""Four smoke tests covering the parts that would silently break.

Deliberately not a full suite. These cover the logic where a regression would
be invisible until a demo: chunk/page mapping, the security boundary on
calculate, SSE frame integrity, and the shape of an agent run.

    pytest -q
"""
from __future__ import annotations

import asyncio
import json

import pytest

from backend import agent, tools
from backend.ingest import build_chunks, chunk_text
from backend.llm import FunctionCall, LLMResponse
from backend.models import Event
from backend.store import Chunk, Document, VectorStore


# --------------------------------------------------------------------------
# 1. chunking keeps page numbers, honours the size budget, and overlaps
# --------------------------------------------------------------------------


def test_chunking_preserves_pages_and_overlaps():
    page_one = "\n\n".join(f"Clause {i}. " + ("regulatory text " * 20) for i in range(1, 6))
    page_two = "Short second page about wire transfers."
    pages = [(1, page_one), (7, page_two)]

    chunks = build_chunks("doc-1", "sample.pdf", pages)

    assert len(chunks) > 2, "a long page should produce several chunks"

    # Page numbers must survive the whole pipeline or citations are worthless.
    assert {c.page_num for c in chunks} == {1, 7}
    assert all(c.doc_id == "doc-1" and c.filename == "sample.pdf" for c in chunks)
    assert len({c.chunk_id for c in chunks}) == len(chunks), "chunk ids must be unique"

    # Body stays within budget; the carried overlap may push it to size+overlap.
    page_one_chunks = [c for c in chunks if c.page_num == 1]
    assert all(len(c.text) <= 800 + 150 for c in page_one_chunks)

    # Consecutive chunks share text, so a sentence on a boundary is not lost.
    first, second = page_one_chunks[0], page_one_chunks[1]
    tail_words = first.text.split()[-8:]
    assert any(word in second.text for word in tail_words)

    assert chunk_text("") == []


# --------------------------------------------------------------------------
# 2. calculate evaluates arithmetic and refuses everything else
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("50000 * 40", 2_000_000.0),
        ("(120 + 30) / 3", 50.0),
        ("2 ** 10", 1024.0),
        ("-17 + 4", -13.0),
        ("100 % 7", 2.0),
    ],
)
def test_calculate_evaluates_plain_arithmetic(expression, expected):
    assert tools._safe_eval(expression) == pytest.approx(expected)


@pytest.mark.parametrize(
    "hostile",
    [
        "__import__('os').system('ls')",   # the classic eval() RCE
        "open('/etc/passwd').read()",
        "(1).__class__.__bases__",
        "[x for x in range(10)]",
        "len('abc')",
        "lambda: 1",
        "9 ** 9 ** 9",                     # DoS with no call node at all
        "1/0",
        "'a' * 5",
    ],
)
def test_calculate_rejects_anything_that_is_not_arithmetic(hostile):
    """The AST walk runs before evaluation, so nothing hostile ever executes."""
    with pytest.raises(tools.ToolError):
        tools._safe_eval(hostile)


# --------------------------------------------------------------------------
# 3. every event serialises to exactly one parseable SSE frame
# --------------------------------------------------------------------------


def test_sse_frames_are_single_and_parseable():
    events = [
        Event(type="thinking", content="Line one.\nLine two with a } brace."),
        Event(type="tool_call", call_id="c1", tool="search_documents", args={"query": "kyc"}),
        Event(type="tool_result", call_id="c1", tool="search_documents", result={"hits": 5}, duration_ms=312),
        Event(type="done", steps=3, elapsed_ms=4120, truncated=False),
    ]

    for event in events:
        frame = event.to_sse()
        assert frame.endswith("\n\n")
        # A literal newline inside the payload would split the frame in two.
        assert frame.count("\n\n") == 1
        body = frame[len("data: ") : -2]
        assert "\n" not in body
        parsed = json.loads(body)
        assert parsed["type"] == event.type

    # Unset fields are dropped rather than sent as nulls.
    assert "citations" not in json.loads(events[0].to_sse()[6:-2])


# --------------------------------------------------------------------------
# 4. the agent loop produces the expected step sequence against a mock LLM
# --------------------------------------------------------------------------


class _ScriptedLLM:
    """Replays a fixed list of LLMResponses so the loop can be tested offline."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    async def __call__(self, *args, **kwargs):
        self.calls += 1
        return self._responses.pop(0)


@pytest.fixture
def seeded_store(monkeypatch, tmp_path):
    store = VectorStore(index_dir=tmp_path)
    store._documents["d1"] = Document(
        doc_id="d1",
        filename="rbi_kyc.pdf",
        num_pages=9,
        num_chunks=1,
        uploaded_at="2026-01-01T00:00:00+00:00",
    )
    store._chunks = [
        Chunk(
            chunk_id="d1:3:0",
            doc_id="d1",
            filename="rbi_kyc.pdf",
            page_num=3,
            text="Customer Due Diligence applies at or above Rupees 50,000.",
        )
    ]
    monkeypatch.setattr(agent, "STORE", store)
    monkeypatch.setattr(tools, "STORE", store)
    return store


def test_agent_loop_chains_tools_and_emits_a_trace(monkeypatch, seeded_store):
    scripted = _ScriptedLLM(
        [
            LLMResponse(
                text="First I need the threshold from the documents.",
                function_calls=[FunctionCall("search_documents", {"query": "CDD threshold"}, "c1")],
            ),
            LLMResponse(
                text="Now I multiply it by 40.",
                function_calls=[FunctionCall("calculate", {"expression": "50000 * 40"}, "c2")],
            ),
            LLMResponse(
                text="The threshold is Rs 50,000 [rbi_kyc.pdf, p.3]; 40 such "
                "transactions total Rs 2,000,000 [rbi_kyc.pdf, p.3].",
            ),
        ]
    )
    monkeypatch.setattr(agent.llm, "generate", scripted)

    async def fake_search(query, top_k=5):
        return [
            {
                "chunk_id": "d1:3:0",
                "doc_id": "d1",
                "filename": "rbi_kyc.pdf",
                "page_num": 3,
                "text": "Customer Due Diligence applies at or above Rupees 50,000.",
                "score": 0.81,
            }
        ]

    monkeypatch.setitem(tools._DISPATCH, "search_documents", fake_search)

    async def run():
        return [e async for e in agent.run_agent("s1", "What is the threshold times 40?")]

    events = asyncio.run(run())
    kinds = [e.type for e in events]

    assert kinds == [
        "thinking",
        "tool_call",
        "tool_result",
        "thinking",
        "tool_call",
        "tool_result",
        "answer",
        "done",
    ]

    tool_calls = [e for e in events if e.type == "tool_call"]
    assert [e.tool for e in tool_calls] == ["search_documents", "calculate"]

    results = [e for e in events if e.type == "tool_result"]
    assert results[0].result["hits"] == 1
    assert results[1].result["value"] == pytest.approx(2_000_000.0)
    assert all(isinstance(e.duration_ms, int) for e in results)

    answer = next(e for e in events if e.type == "answer")
    assert [(c.filename, c.page) for c in answer.citations] == [("rbi_kyc.pdf", 3)]

    done = events[-1]
    assert done.steps == 3 and done.truncated is False


def test_tool_failure_does_not_kill_the_run(monkeypatch, seeded_store):
    """A raising tool is reported to the model, not propagated to the client."""
    scripted = _ScriptedLLM(
        [
            LLMResponse(
                text="Let me compute that.",
                function_calls=[FunctionCall("calculate", {"expression": "import os"}, "c1")],
            ),
            LLMResponse(text="That expression was not valid arithmetic."),
        ]
    )
    monkeypatch.setattr(agent.llm, "generate", scripted)

    async def run():
        return [e async for e in agent.run_agent("s2", "compute something odd")]

    events = asyncio.run(run())
    result = next(e for e in events if e.type == "tool_result")

    assert "error" in result.result
    assert events[-1].type == "done"
    assert any(e.type == "answer" for e in events)
