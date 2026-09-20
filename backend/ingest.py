"""PDF -> pages -> chunks -> embeddings -> FAISS.

The one non-negotiable in here is the page number. It is captured at
extraction and carried on every chunk all the way through retrieval, because
a citation without a page is not a citation -- nobody can check it.

Run standalone:
    python -m backend.ingest data/samples/rbi_kyc_master_direction.pdf
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
from pypdf import PdfReader

from . import config, llm
from .store import STORE, Chunk, Document

log = logging.getLogger("agenttrace.ingest")

_WS = re.compile(r"[ \t\r\f\v]+")
_MULTI_NEWLINE = re.compile(r"\n{2,}")
_SENTENCE_END = re.compile(r"(?<=[.!?;:])\s+")


class IngestError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# extraction
# --------------------------------------------------------------------------


def _clean(text: str) -> str:
    """Normalise the usual PDF extraction debris without destroying layout."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("­", "")            # soft hyphens
    text = re.sub(r"-\n(?=[a-z])", "", text)     # de-hyphenate across line breaks
    text = _WS.sub(" ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = _MULTI_NEWLINE.sub("\n\n", text)
    return text.strip()


def extract_pages(pdf_path: Path) -> list[tuple[int, str]]:
    """Return [(page_num, text)] with 1-based page numbers, empties dropped."""
    try:
        reader = PdfReader(str(pdf_path))
    except Exception as exc:
        raise IngestError(f"Could not open PDF: {exc}") from exc

    if reader.is_encrypted:
        try:
            reader.decrypt("")  # many PDFs are encrypted with an empty password
        except Exception as exc:
            raise IngestError("PDF is password protected.") from exc

    pages: list[tuple[int, str]] = []
    for page_num, page in enumerate(reader.pages, start=1):
        try:
            raw = page.extract_text() or ""
        except Exception as exc:
            log.warning("page %d of %s failed to extract: %s", page_num, pdf_path.name, exc)
            raw = ""
        cleaned = _clean(raw)
        if cleaned:
            pages.append((page_num, cleaned))

    if not pages:
        raise IngestError(
            "No extractable text found. This looks like a scanned PDF - "
            "OCR is out of scope for this project."
        )
    return pages


# --------------------------------------------------------------------------
# chunking
# --------------------------------------------------------------------------


def _hard_window(text: str, size: int) -> list[str]:
    """Last resort for a single run of text longer than one chunk."""
    return [text[i : i + size].strip() for i in range(0, len(text), size) if text[i : i + size].strip()]


def _split_oversized(paragraph: str, size: int) -> list[str]:
    """Break one over-long paragraph on sentence boundaries first."""
    pieces: list[str] = []
    buffer = ""
    for sentence in _SENTENCE_END.split(paragraph):
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) > size:
            if buffer:
                pieces.append(buffer)
                buffer = ""
            pieces.extend(_hard_window(sentence, size))
            continue
        candidate = f"{buffer} {sentence}".strip()
        if len(candidate) > size and buffer:
            pieces.append(buffer)
            buffer = sentence
        else:
            buffer = candidate
    if buffer:
        pieces.append(buffer)
    return pieces


def _overlap_tail(text: str, overlap: int) -> str:
    """Trailing `overlap` characters, trimmed forward to a word boundary."""
    if overlap <= 0 or len(text) <= overlap:
        return text
    tail = text[-overlap:]
    space = tail.find(" ")
    return tail[space + 1 :] if space != -1 else tail


def chunk_text(
    text: str,
    size: int = config.CHUNK_SIZE,
    overlap: int = config.CHUNK_OVERLAP,
) -> list[str]:
    """Pack paragraphs into ~`size`-character chunks with `overlap` carried over.

    Paragraph boundaries are preferred over sentence boundaries, and sentence
    boundaries over a hard cut, so a chunk is as close to one coherent idea as
    the source allows. Chunks can run up to size+overlap once the carried tail
    is prepended -- that is intended, not a bug.
    """
    text = text.strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) == 1 and len(paragraphs[0]) > size:
        paragraphs = [p.strip() for p in paragraphs[0].split("\n") if p.strip()]

    units: list[str] = []
    for paragraph in paragraphs:
        units.extend(_split_oversized(paragraph, size) if len(paragraph) > size else [paragraph])

    chunks: list[str] = []
    buffer = ""
    for unit in units:
        candidate = f"{buffer}\n{unit}".strip() if buffer else unit
        if len(candidate) > size and buffer:
            chunks.append(buffer)
            carried = _overlap_tail(buffer, overlap)
            buffer = f"{carried}\n{unit}".strip() if carried else unit
        else:
            buffer = candidate
    if buffer:
        chunks.append(buffer)

    return [c for c in chunks if c.strip()]


def build_chunks(doc_id: str, filename: str, pages: list[tuple[int, str]]) -> list[Chunk]:
    """Chunk page by page so every chunk inherits exactly one page number."""
    chunks: list[Chunk] = []
    for page_num, page_text in pages:
        for piece in chunk_text(page_text):
            chunks.append(
                Chunk(
                    chunk_id=f"{doc_id}:{page_num}:{len(chunks)}",
                    doc_id=doc_id,
                    filename=filename,
                    page_num=page_num,
                    text=piece,
                )
            )
    return chunks


def make_doc_id(filename: str, payload: bytes) -> str:
    """Content-addressed, so re-uploading the same file is idempotent."""
    digest = hashlib.sha256(payload).hexdigest()[:10]
    stem = re.sub(r"[^a-z0-9]+", "-", Path(filename).stem.lower()).strip("-") or "doc"
    return f"{stem[:40]}-{digest}"


# --------------------------------------------------------------------------
# pipeline
# --------------------------------------------------------------------------


async def ingest_pdf(pdf_path: Path, filename: str | None = None) -> Document:
    """Full pipeline for one PDF. Returns the registered Document."""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise IngestError(f"File not found: {pdf_path}")

    payload = pdf_path.read_bytes()
    if len(payload) > config.MAX_UPLOAD_BYTES:
        raise IngestError(
            f"File is {len(payload) / 1e6:.1f} MB; the limit is "
            f"{config.MAX_UPLOAD_BYTES / 1e6:.0f} MB."
        )

    display_name = filename or pdf_path.name
    doc_id = make_doc_id(display_name, payload)

    existing = STORE.get_document(doc_id)
    if existing:
        log.info("%s already indexed (%d chunks)", display_name, existing.num_chunks)
        return existing

    pages = extract_pages(pdf_path)
    chunks = build_chunks(doc_id, display_name, pages)
    if not chunks:
        raise IngestError("PDF produced no chunks.")

    log.info("embedding %d chunks from %s ...", len(chunks), display_name)
    vectors = await llm.embed_texts([c.text for c in chunks], task_type="RETRIEVAL_DOCUMENT")
    matrix = np.asarray(vectors, dtype="float32")

    return STORE.add_document(
        doc_id=doc_id,
        filename=display_name,
        num_pages=pages[-1][0],
        chunks=chunks,
        vectors=matrix,
    )


async def _main(paths: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    STORE.load_from_disk()
    for raw in paths:
        try:
            document = await ingest_pdf(Path(raw))
        except Exception as exc:
            print(f"FAILED {raw}: {exc}", file=sys.stderr)
            return 1
        print(
            f"OK  {document.filename}: {document.num_pages} pages -> "
            f"{document.num_chunks} chunks  (doc_id={document.doc_id})"
        )
    print(f"\nIndex now holds {STORE.num_chunks} chunks across {STORE.doc_count()} document(s).")
    await llm.aclose()
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m backend.ingest <file.pdf> [more.pdf ...]", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(asyncio.run(_main(sys.argv[1:])))
