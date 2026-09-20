# --------------------------------------------------------------------------
# Stage 1 - build the React app
# --------------------------------------------------------------------------
FROM node:20-alpine AS frontend

WORKDIR /app/frontend
COPY frontend/package.json ./
RUN npm install --no-audit --no-fund

COPY frontend/ ./
RUN npm run build


# --------------------------------------------------------------------------
# Stage 2 - runtime. Python deps + the built static files, nothing else.
# Node and the whole node_modules tree stay in stage 1.
# --------------------------------------------------------------------------
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY data/samples/ ./data/samples/

# The built SPA is served by FastAPI from the same origin as the API, so there
# is one deploy, one URL and no CORS configuration.
COPY --from=frontend /app/frontend/dist ./backend/static

# Hugging Face Spaces runs the container as uid 1000; the index and upload
# directories have to be writable by that user.
RUN useradd -m -u 1000 appuser \
    && mkdir -p /app/data/index /app/data/uploads \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:7860/api/health',timeout=4).status==200 else 1)"

# One worker on purpose: the document registry and FAISS index live in this
# process's memory, so a second worker would serve a different corpus.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
