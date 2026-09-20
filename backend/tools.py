"""The three tools the agent can call, plus their Gemini function schemas.

A tool's `description` is a prompt, not documentation: it is the only thing
the model reads when deciding what to call. Vague descriptions produce bad
tool selection far more often than a weak model does.

Security note on `calculate`: its argument is a string produced by an LLM,
which makes it untrusted user input. It is evaluated by walking a parsed AST
against an allowlist. `eval()` and `exec()` are never used -- see _safe_eval.
"""
from __future__ import annotations

import ast
import asyncio
import logging
from typing import Any

from . import config, llm
from .store import STORE

log = logging.getLogger("agenttrace.tools")


class ToolError(RuntimeError):
    """Raised for bad arguments. The message is fed back to the model so it
    can correct itself, so it must read as an instruction, not a stack trace."""


# ==========================================================================
# 1. search_documents
# ==========================================================================


async def search_documents(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """Embed the query and pull the nearest chunks out of the flat index."""
    query = (query or "").strip()
    if not query:
        raise ToolError("query must be a non-empty string.")
    if STORE.num_chunks == 0:
        raise ToolError("No documents have been indexed yet. Ask the user to upload a PDF.")

    top_k = max(1, min(int(top_k or 5), 10))
    vector = await llm.embed_query(query)
    hits = STORE.search(vector, top_k=top_k)

    return [
        {
            "chunk_id": chunk.chunk_id,
            "doc_id": chunk.doc_id,
            "filename": chunk.filename,
            "page_num": chunk.page_num,
            "text": chunk.text,
            "score": round(score, 4),
        }
        for chunk, score in hits
    ]


# ==========================================================================
# 2. summarize_section
# ==========================================================================


async def summarize_section(doc_id: str, page_start: int, page_end: int) -> str:
    """Concatenate a page range and compress it with one LLM call."""
    resolved = STORE.resolve_doc_id(str(doc_id or ""))
    if resolved is None:
        known = ", ".join(d.filename for d in STORE.documents()) or "none"
        raise ToolError(f"Unknown document '{doc_id}'. Indexed documents: {known}.")

    try:
        page_start, page_end = int(page_start), int(page_end)
    except (TypeError, ValueError):
        raise ToolError("page_start and page_end must be integers.") from None

    if page_start > page_end:
        page_start, page_end = page_end, page_start
    span = page_end - page_start + 1
    if span > config.SUMMARY_MAX_PAGES:
        raise ToolError(
            f"Range of {span} pages is too wide; summarize at most "
            f"{config.SUMMARY_MAX_PAGES} pages at a time."
        )

    document = STORE.get_document(resolved)
    selected = [
        c for c in STORE.chunks_for_doc(resolved) if page_start <= c.page_num <= page_end
    ]
    if not selected:
        raise ToolError(
            f"No text found in {document.filename} between pages {page_start} and "
            f"{page_end} (the document has {document.num_pages} pages)."
        )

    body = "\n\n".join(f"[p.{c.page_num}] {c.text}" for c in selected)
    prompt = (
        "Summarise the regulatory text below. Preserve every specific obligation, "
        "monetary threshold, time limit and defined term exactly as written, and keep "
        "the [p.N] page marker next to each fact you carry over. Do not add anything "
        "that is not in the text.\n\n"
        f"--- {document.filename}, pages {page_start}-{page_end} ---\n{body}"
    )

    response = await llm.generate(
        contents=[{"role": "user", "parts": [{"text": prompt}]}],
        temperature=0.1,
    )
    summary = response.text.strip()
    if not summary:
        raise ToolError("The summariser returned nothing; try a narrower page range.")
    return summary


# ==========================================================================
# 3. calculate  --  the one that has to be airtight
# ==========================================================================

# Node types that can appear in an arithmetic expression and nothing else.
# Name, Call, Attribute and Subscript are all absent, which is what makes
# `__import__('os').system('rm -rf /')` -- a perfectly valid Python
# expression -- fail at parse-walk time instead of running.
_ALLOWED_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Constant,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.Mod,
    ast.USub,
    ast.UAdd,
)

_MAX_EXPRESSION_LEN = 200
_MAX_EXPONENT = 64          # 2 ** 1e9 is a denial of service with no call node
_MAX_MAGNITUDE = 1e15


def _check_node(node: ast.AST) -> None:
    if not isinstance(node, _ALLOWED_NODES):
        raise ToolError(
            f"'{type(node).__name__}' is not allowed. calculate accepts plain "
            "arithmetic only: numbers with + - * / ** % and parentheses."
        )
    if isinstance(node, ast.Constant):
        # bool is a subclass of int, so it is rejected explicitly.
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ToolError("Only numeric literals are allowed.")
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
        exponent = node.right
        if isinstance(exponent, ast.UnaryOp) and isinstance(exponent.op, ast.USub):
            exponent = exponent.operand
        if not isinstance(exponent, ast.Constant) or abs(exponent.value) > _MAX_EXPONENT:
            raise ToolError(
                f"Exponents must be numeric literals no larger than {_MAX_EXPONENT}."
            )


def _safe_eval(expression: str) -> float:
    """Parse to an AST, reject anything outside the allowlist, then fold it.

    The walk happens before any arithmetic runs, so a hostile expression never
    reaches evaluation at all.
    """
    expression = (expression or "").strip()
    if not expression:
        raise ToolError("expression must be a non-empty string.")
    if len(expression) > _MAX_EXPRESSION_LEN:
        raise ToolError(f"Expression is too long (limit {_MAX_EXPRESSION_LEN} characters).")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ToolError(f"Could not parse '{expression}': {exc.msg}.") from None

    for node in ast.walk(tree):
        _check_node(node)

    def evaluate(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant):
            return float(node.value)
        if isinstance(node, ast.UnaryOp):
            value = evaluate(node.operand)
            return -value if isinstance(node.op, ast.USub) else +value
        if isinstance(node, ast.BinOp):
            left, right = evaluate(node.left), evaluate(node.right)
            if isinstance(node.op, ast.Add):
                result = left + right
            elif isinstance(node.op, ast.Sub):
                result = left - right
            elif isinstance(node.op, ast.Mult):
                result = left * right
            elif isinstance(node.op, ast.Div):
                if right == 0:
                    raise ToolError("Division by zero.")
                result = left / right
            elif isinstance(node.op, ast.Mod):
                if right == 0:
                    raise ToolError("Modulo by zero.")
                result = left % right
            elif isinstance(node.op, ast.Pow):
                result = left**right
            else:  # pragma: no cover - unreachable given the allowlist
                raise ToolError(f"Unsupported operator {type(node.op).__name__}.")
            if abs(result) > _MAX_MAGNITUDE:
                raise ToolError(f"Result exceeds the magnitude limit of {_MAX_MAGNITUDE:g}.")
            return result
        raise ToolError(f"Unsupported node {type(node).__name__}.")  # pragma: no cover

    try:
        return float(evaluate(tree))
    except OverflowError:
        raise ToolError("Result is too large to represent.") from None


async def calculate(expression: str) -> float:
    return _safe_eval(expression)


# ==========================================================================
# schemas + dispatch
# ==========================================================================

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "search_documents",
        "description": (
            "Semantic search over every indexed PDF. Returns the most relevant text "
            "chunks with their filename, page number and similarity score. Use this "
            "before answering any question about the documents. If the results do not "
            "contain what you need, call it again with different wording - synonyms, "
            "the regulator's own terminology, or a narrower phrase."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "Natural-language search phrase, e.g. 'customer due diligence monetary threshold'.",
                },
                "top_k": {
                    "type": "INTEGER",
                    "description": "How many chunks to return, 1-10. Default 5.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "summarize_section",
        "description": (
            "Condense a contiguous page range of one document into a summary that "
            "preserves thresholds, obligations and defined terms. Use this when a "
            "question is about a whole section rather than a specific fact, and only "
            "after search_documents has told you which pages matter. Maximum 10 pages."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "doc_id": {
                    "type": "STRING",
                    "description": "doc_id or filename, exactly as returned by search_documents.",
                },
                "page_start": {"type": "INTEGER", "description": "First page, 1-based, inclusive."},
                "page_end": {"type": "INTEGER", "description": "Last page, inclusive. At most 10 pages from page_start."},
            },
            "required": ["doc_id", "page_start", "page_end"],
        },
    },
    {
        "name": "calculate",
        "description": (
            "Evaluate one arithmetic expression and return the number. Use this for "
            "every calculation instead of working it out yourself - totals, "
            "percentages, multiples of a threshold. Accepts numbers with + - * / ** % "
            "and parentheses only. Pass digits, never currency symbols, commas or units: "
            "write '50000 * 40', not 'Rs 50,000 x 40'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "expression": {
                    "type": "STRING",
                    "description": "A plain arithmetic expression, e.g. '50000 * 40'.",
                }
            },
            "required": ["expression"],
        },
    },
]

_DISPATCH = {
    "search_documents": search_documents,
    "summarize_section": summarize_section,
    "calculate": calculate,
}

TOOL_NAMES = tuple(_DISPATCH)


async def dispatch(name: str, args: dict[str, Any]) -> Any:
    """Route a model-chosen tool call to its implementation.

    Unknown names and bad signatures are turned into ToolError so the agent
    loop can hand the message back to the model rather than dying.
    """
    func = _DISPATCH.get(name)
    if func is None:
        raise ToolError(f"Unknown tool '{name}'. Available: {', '.join(TOOL_NAMES)}.")
    try:
        return await func(**(args or {}))
    except ToolError:
        raise
    except TypeError as exc:
        raise ToolError(f"Bad arguments for {name}: {exc}") from None
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - a tool must never kill the loop
        log.exception("tool %s failed", name)
        raise ToolError(f"{name} failed: {exc}") from None
