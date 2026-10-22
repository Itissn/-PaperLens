FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 libstdc++6 \
    && rm -rf /var/lib/apt/lists/*
LABEL org.opencontainers.image.source="https://github.com/Itissn/-PaperLens"
WORKDIR /app
COPY requirements-container.txt .
RUN pip install --no-cache-dir -r requirements-container.txt && pip check
COPY paperlens ./paperlens
COPY web ./web
COPY scripts/download_corpus.py scripts/setup_reranker.py scripts/setup_nli.py scripts/container_bootstrap.py scripts/container-assets.json ./scripts/
COPY manage.py ./
RUN useradd --uid 10001 --create-home appuser \
    && mkdir -p /app/data /app/reports /app/.cache \
    && chown -R 10001:10001 /app/data /app/reports /app/.cache
USER 10001:10001
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 \
    PAPERLENS_AUTH_REQUIRED=1 PAPERLENS_STRICT_READINESS=1 \
    HF_HOME=/app/.cache/hf HF_HUB_DISABLE_XET=1 XDG_CACHE_HOME=/app/.cache \
    OMP_NUM_THREADS=4 TOKENIZERS_PARALLELISM=false
HEALTHCHECK --interval=15s --timeout=5s --start-period=120s --retries=4 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/readiness',timeout=4)"
EXPOSE 8765
CMD ["python", "-m", "uvicorn", "paperlens.api:app", "--host", "0.0.0.0", "--port", "8765"]
