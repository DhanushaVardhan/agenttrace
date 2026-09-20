"""In-memory document registry + FAISS vector index.

Scope note: this is deliberately not a database. The corpus is a handful of
PDFs, the process is single-user, and an in-memory dict plus JSON on disk is
the honest choice at this size. Swapping in pgvector or Qdrant means
reimplementing this one class.

Index choice: IndexFlatIP over L2-normalised vectors. Normalising makes inner
product identical to cosine similarity, which is the right metric for text.
Flat is exhaustive, so recall is exactly 1.0 -- approximate indexes (HNSW,
IVF) only start paying for themselves somewhere north of a million vectors,
and below that they trade recall away for speed you do not need.
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import config

log = logging.getLogger("agenttrace.store")

try:
    import faiss  # type: ignore

    _HAS_FAISS = True
except ImportError:  # pragma: no cover
    faiss = None  # type: ignore
    _HAS_FAISS = False
    log.warning("faiss-cpu not installed - falling back to a numpy brute-force index.")


# --------------------------------------------------------------------------
# index backend
# --------------------------------------------------------------------------


class _NumpyFlatIP:
    """Fallback with the slice of the FAISS API this project uses.

    Exists so tests and local development run without the faiss wheel. The
    maths is identical -- a dot product against a matrix -- so behaviour does
    not change, only speed at scale.
    """

    def __init__(self, dim: int) -> None:
        self.d = dim
        self._vectors = np.zeros((0, dim), dtype="float32")

    @property
    def ntotal(self) -> int:
        return int(self._vectors.shape[0])

    def add(self, vectors: np.ndarray) -> None:
        self._vectors = np.vstack([self._vectors, vectors.astype("float32")])

    def search(self, queries: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
        if self.ntotal == 0:
            empty = np.full((queries.shape[0], k), -1, dtype="int64")
            return np.zeros((queries.shape[0], k), dtype="float32"), empty
        scores = queries.astype("float32") @ self._vectors.T
        k = min(k, self.ntotal)
        idx = np.argsort(-scores, axis=1)[:, :k]
        top = np.take_along_axis(scores, idx, axis=1)
        return top.astype("float32"), idx.astype("int64")


def _new_index(dim: int):
    return faiss.IndexFlatIP(dim) if _HAS_FAISS else _NumpyFlatIP(dim)


def normalize(vectors: np.ndarray) -> np.ndarray:
    """L2-normalise rows so inner product == cosine similarity."""
    vectors = np.asarray(vectors, dtype="float32")
    if vectors.ndim == 1:
        vectors = vectors.reshape(1, -1)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0  # a zero vector would otherwise produce NaN
    return vectors / norms


# --------------------------------------------------------------------------
# records
# --------------------------------------------------------------------------


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    filename: str
    page_num: int
    text: str


@dataclass
class Document:
    doc_id: str
    filename: str
    num_pages: int
    num_chunks: int
    uploaded_at: str


class VectorStore:
    """Registry of documents plus the flat index over all their chunks.

    The index holds every chunk from every document in one flat space, with
    `self._chunks[i]` describing row `i`. Deleting a document therefore means
    rebuilding: with a few thousand vectors that is milliseconds, and it keeps
    the row/metadata mapping impossible to corrupt.
    """

    def __init__(self, index_dir: Path | None = None) -> None:
        self.index_dir = Path(index_dir or config.INDEX_DIR)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._documents: dict[str, Document] = {}
        self._chunks: list[Chunk] = []
        self._vectors: dict[str, np.ndarray] = {}  # doc_id -> (n, dim) normalised
        self._index = None
        self._dim: int | None = None

    # -- properties --------------------------------------------------------

    @property
    def dim(self) -> int | None:
        return self._dim

    @property
    def num_chunks(self) -> int:
        return len(self._chunks)

    def documents(self) -> list[Document]:
        return sorted(self._documents.values(), key=lambda d: d.uploaded_at)

    def doc_count(self) -> int:
        return len(self._documents)

    def get_document(self, doc_id: str) -> Document | None:
        return self._documents.get(doc_id)

    def chunks_for_doc(self, doc_id: str) -> list[Chunk]:
        return [c for c in self._chunks if c.doc_id == doc_id]

    def resolve_doc_id(self, ref: str) -> str | None:
        """Accept a doc_id or a filename, because the model will use either."""
        if ref in self._documents:
            return ref
        low = ref.strip().lower()
        for doc in self._documents.values():
            if doc.filename.lower() == low or Path(doc.filename).stem.lower() == low:
                return doc.doc_id
        return None

    # -- mutation ----------------------------------------------------------

    def add_document(
        self,
        doc_id: str,
        filename: str,
        num_pages: int,
        chunks: list[Chunk],
        vectors: np.ndarray,
    ) -> Document:
        if len(chunks) != len(vectors):
            raise ValueError("chunk/vector count mismatch")

        normalised = normalize(vectors)
        with self._lock:
            if self._dim is None:
                # Dimension is learned from the data, so changing embedding
                # model is an env var, not a code change.
                self._dim = int(normalised.shape[1])
            elif normalised.shape[1] != self._dim:
                raise ValueError(
                    f"Embedding dimension {normalised.shape[1]} does not match the "
                    f"existing index ({self._dim}). Clear data/index to switch models."
                )

            document = Document(
                doc_id=doc_id,
                filename=filename,
                num_pages=num_pages,
                num_chunks=len(chunks),
                uploaded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
            self._documents[doc_id] = document
            self._vectors[doc_id] = normalised
            self._persist_document(document, chunks, normalised)
            self._rebuild_unlocked()
        return document

    def delete_document(self, doc_id: str) -> bool:
        with self._lock:
            if doc_id not in self._documents:
                return False
            self._documents.pop(doc_id)
            self._vectors.pop(doc_id, None)
            for suffix in (".json", ".npy"):
                path = self.index_dir / f"{doc_id}{suffix}"
                path.unlink(missing_ok=True)
            self._rebuild_unlocked()
        return True

    # -- search ------------------------------------------------------------

    def search(self, query_vector: np.ndarray, top_k: int = 5) -> list[tuple[Chunk, float]]:
        if self._index is None or self.num_chunks == 0:
            return []
        query = normalize(np.asarray(query_vector, dtype="float32"))
        scores, indices = self._index.search(query, min(top_k, self.num_chunks))
        hits: list[tuple[Chunk, float]] = []
        for row_idx, score in zip(indices[0], scores[0]):
            if row_idx < 0:
                continue
            hits.append((self._chunks[int(row_idx)], float(score)))
        return hits

    # -- persistence -------------------------------------------------------

    def _persist_document(
        self, document: Document, chunks: list[Chunk], vectors: np.ndarray
    ) -> None:
        meta = {
            "document": asdict(document),
            "chunks": [asdict(c) for c in chunks],
        }
        (self.index_dir / f"{document.doc_id}.json").write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8"
        )
        np.save(self.index_dir / f"{document.doc_id}.npy", vectors)

    def _rebuild_unlocked(self) -> None:
        """Rebuild the flat index and the row -> chunk mapping together."""
        self._chunks = []
        if not self._documents:
            self._index = None
            self._write_index()
            return

        ordered = sorted(self._documents.values(), key=lambda d: d.uploaded_at)
        matrices: list[np.ndarray] = []
        for document in ordered:
            chunk_meta = self._load_chunks(document.doc_id)
            vectors = self._vectors.get(document.doc_id)
            if vectors is None or len(chunk_meta) != len(vectors):
                log.warning("skipping %s: chunk/vector mismatch on rebuild", document.doc_id)
                continue
            self._chunks.extend(chunk_meta)
            matrices.append(vectors)

        if not matrices:
            self._index = None
            return

        stacked = np.vstack(matrices).astype("float32")
        self._dim = int(stacked.shape[1])
        self._index = _new_index(self._dim)
        self._index.add(stacked)
        self._write_index()

    def _load_chunks(self, doc_id: str) -> list[Chunk]:
        path = self.index_dir / f"{doc_id}.json"
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return [Chunk(**c) for c in data.get("chunks", [])]

    def _write_index(self) -> None:
        """Warm-start artefact. Rebuilding from .npy is authoritative."""
        if not _HAS_FAISS:
            return
        path = self.index_dir / "index.faiss"
        try:
            if self._index is None:
                path.unlink(missing_ok=True)
            else:
                faiss.write_index(self._index, str(path))
        except Exception as exc:  # pragma: no cover - disk issues are not fatal
            log.warning("could not persist faiss index: %s", exc)

    def load_from_disk(self) -> None:
        """Restore whatever survived a restart. Uploads are not persisted, so
        this only ever repopulates what a previous run indexed."""
        with self._lock:
            self._documents.clear()
            self._vectors.clear()
            for meta_path in sorted(self.index_dir.glob("*.json")):
                try:
                    data = json.loads(meta_path.read_text(encoding="utf-8"))
                    document = Document(**data["document"])
                    vec_path = self.index_dir / f"{document.doc_id}.npy"
                    if not vec_path.exists():
                        continue
                    self._documents[document.doc_id] = document
                    self._vectors[document.doc_id] = np.load(vec_path)
                except Exception as exc:
                    log.warning("skipping unreadable index file %s: %s", meta_path.name, exc)
            self._rebuild_unlocked()
        if self._documents:
            log.info(
                "restored %d document(s), %d chunk(s) from disk",
                len(self._documents),
                self.num_chunks,
            )


# Single process-wide store. Explicitly not thread-safe for writes beyond the
# lock above, and explicitly not multi-worker safe -- run uvicorn with one worker.
STORE = VectorStore()
