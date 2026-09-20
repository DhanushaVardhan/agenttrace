"""Central configuration, read once from the environment.

Everything is env-driven so the same image runs locally and on Hugging Face
Spaces, where GEMINI_API_KEY arrives as a Space secret.
"""
from __future__ import annotations

import os
from pathlib import Path

try:  # optional: lets `python -m backend.ingest` pick up a local .env
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - dotenv is a convenience, not a need
    pass

# --- paths -----------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
SAMPLES_DIR = DATA_DIR / "samples"
INDEX_DIR = DATA_DIR / "index"
UPLOAD_DIR = DATA_DIR / "uploads"
STATIC_DIR = Path(__file__).resolve().parent / "static"

for _d in (INDEX_DIR, UPLOAD_DIR, SAMPLES_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --- models ----------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# text-embedding-004 was retired and now 404s on embedContent. gemini-embedding-001
# replaces it. Note that batchEmbedContents still works for it even though the
# model's supportedGenerationMethods does not advertise the method.
EMBED_MODEL = os.getenv("EMBED_MODEL", "gemini-embedding-001")

# gemini-embedding-001 returns 3072 dimensions by default. It is trained with
# Matryoshka representation learning, so a 768-dimension truncation keeps
# almost all of the retrieval quality at a quarter of the memory - which
# matters on a 512 MB free instance. Google returns UNNORMALISED vectors for
# any dimension other than 3072, so normalising is mandatory here rather than
# merely convenient; store.normalize() does it on every insert and query.
EMBED_DIM = int(os.getenv("EMBED_DIM", "768"))
GEMINI_BASE_URL = os.getenv(
    "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
)

# --- ingestion knobs -------------------------------------------------------
# 800 chars holds a complete regulatory clause without diluting the embedding
# across topics; 150 of overlap stops a sentence that straddles a chunk
# boundary from being lost to both sides.
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))
EMBED_BATCH_SIZE = 100  # batchEmbedContents caps requests at 100
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB

# --- agent knobs -----------------------------------------------------------
MAX_STEPS = int(os.getenv("MAX_STEPS", "6"))
TOOL_RESULT_CHAR_LIMIT = 2000  # what we stream to the UI, not what the model sees
SUMMARY_MAX_PAGES = 10

PORT = int(os.getenv("PORT", "7860"))


def require_api_key() -> str:
    """Fail loudly and usefully rather than with a 401 from Google."""
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Copy .env.example to .env and add your key, "
            "or set it as a Hugging Face Space secret."
        )
    return GEMINI_API_KEY
