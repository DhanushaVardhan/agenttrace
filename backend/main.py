"""FastAPI app: upload, document registry, the SSE chat stream, and the SPA.

One container serves both the API and the built React app. That is a
deliberate choice: splitting the frontend onto Vercel and the backend onto
Render doubles the number of things that can be down, and buys a CORS
configuration nobody wanted.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import agent, config, llm
from .ingest import IngestError, ingest_pdf
from .models import ChatRequest, DocumentInfo, Event, HealthResponse, UploadResponse
from .store import STORE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("agenttrace.api")

AUTO_INGEST_SAMPLES = os.getenv("AUTO_INGEST_SAMPLES", "true").lower() == "true"


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    STORE.load_from_disk()
    task: asyncio.Task | None = None
    if AUTO_INGEST_SAMPLES and config.GEMINI_API_KEY:
        # Seeds the demo corpus in the background so a cold Space is usable
        # the moment it finishes booting, without blocking the port.
        task = asyncio.create_task(_ingest_samples())
    yield
    if task and not task.done():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    await llm.aclose()


async def _ingest_samples() -> None:
    pdfs = sorted(config.SAMPLES_DIR.glob("*.pdf"))
    if not pdfs:
        return
    log.info("seeding %d sample document(s)...", len(pdfs))
    for path in pdfs:
        try:
            document = await ingest_pdf(path)
            log.info("seeded %s (%d chunks)", document.filename, document.num_chunks)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - seeding must never block startup
            log.warning("could not seed %s: %s", path.name, exc)


app = FastAPI(
    title="AgentTrace",
    version="1.0.0",
    description="Observable agentic RAG over PDFs, with a live reasoning trace.",
    lifespan=lifespan,
)


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok" if config.GEMINI_API_KEY else "missing_api_key",
        doc_count=STORE.doc_count(),
        model=config.GEMINI_MODEL,
    )


@app.get("/api/documents", response_model=list[DocumentInfo])
async def list_documents() -> list[DocumentInfo]:
    return [DocumentInfo(**vars(d)) for d in STORE.documents()]


@app.post("/api/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...)) -> UploadResponse:
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    payload = await file.read()
    if len(payload) == 0:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(payload) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File is {len(payload) / 1e6:.1f} MB; the limit is "
            f"{config.MAX_UPLOAD_BYTES / 1e6:.0f} MB.",
        )

    safe_name = Path(file.filename).name  # strip any directory component
    target = config.UPLOAD_DIR / safe_name
    target.write_bytes(payload)

    try:
        document = await ingest_pdf(target, filename=safe_name)
    except IngestError as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except llm.LLMError as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=502, detail=f"Embedding failed: {exc}") from None

    return UploadResponse(
        doc_id=document.doc_id,
        filename=document.filename,
        num_pages=document.num_pages,
        num_chunks=document.num_chunks,
    )


@app.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: str) -> JSONResponse:
    if not STORE.delete_document(doc_id):
        raise HTTPException(status_code=404, detail="No such document.")
    return JSONResponse({"deleted": doc_id, "remaining_chunks": STORE.num_chunks})


@app.post("/api/chat")
async def chat(payload: ChatRequest, request: Request) -> StreamingResponse:
    """Stream the agent run as SSE frames.

    Unidirectional server -> client, so SSE over plain HTTP rather than a
    WebSocket. It is a POST because the request carries a body, which is also
    why the browser reads it with fetch + ReadableStream instead of EventSource.
    """

    async def stream() -> AsyncGenerator[bytes, None]:
        try:
            async for event in agent.run_agent(payload.session_id, payload.message):
                if await request.is_disconnected():
                    log.info("client disconnected; abandoning run")
                    return
                yield event.to_sse().encode("utf-8")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.exception("stream failed")
            yield Event(type="error", message=str(exc)).to_sse().encode("utf-8")

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # Without this, nginx-style proxies buffer the whole response and
            # the trace arrives all at once at the end, killing the demo.
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/sessions/{session_id}/reset")
async def reset_session(session_id: str) -> JSONResponse:
    agent.reset_session(session_id)
    return JSONResponse({"reset": session_id})


# --------------------------------------------------------------------------
# static SPA -- must be registered last so it never shadows /api/*
# --------------------------------------------------------------------------

_STATIC = config.STATIC_DIR
_INDEX = _STATIC / "index.html"

if (_STATIC / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=_STATIC / "assets"), name="assets")


# response_model=None and a plain Response annotation are both load-bearing.
# FastAPI infers the response model from the return annotation and only skips
# it when `lenient_issubclass(annotation, Response)` holds. A union such as
# `FileResponse | JSONResponse` is a types.UnionType, not a type, so that check
# returns False and FastAPI tries to build a Pydantic field out of it --
# raising FastAPIError at import time, before the server ever starts.
@app.get("/{full_path:path}", include_in_schema=False, response_model=None)
async def spa(full_path: str) -> Response:
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found.")

    candidate = (_STATIC / full_path).resolve()
    if full_path and _STATIC.exists() and candidate.is_file():
        # Path traversal guard: the resolved path must stay inside static/.
        if _STATIC.resolve() in candidate.parents:
            return FileResponse(candidate)

    if _INDEX.exists():
        return FileResponse(_INDEX)

    return JSONResponse(
        status_code=404,
        content={
            "detail": "Frontend not built. Run `npm run build` in frontend/, "
            "or use the Docker image which builds it for you."
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=config.PORT, reload=True)
