# Fieldnote - CPU-only, no GPU required.
#
#   docker build -t fieldnote .
#   docker run -d -p 8000:8000 -v fieldnote-data:/app/data --name fieldnote fieldnote
#
# The corpus is built and indexed on first start, then cached in the volume.
# The models are baked into the image, so the first request is not a 2 GB
# download.

FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_DISABLE_SYMLINKS_WARNING=1 \
    TOKENIZERS_PARALLELISM=false \
    OMP_NUM_THREADS=4 \
    FIELDNOTE_DATA_DIR=/app/data

WORKDIR /app

# libgl1/libglib2.0 are needed by opencv (rapidocr). build-essential is only
# here to compile the few wheels that have no prebuilt wheel.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

# CPU-only torch: the CUDA build is about 2 GB larger and would be unused.
RUN pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu

COPY pyproject.toml README.md ./
COPY fieldnote ./fieldnote
COPY scripts ./scripts
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN pip install --no-cache-dir . \
    && apt-get purge -y build-essential && apt-get autoremove -y \
    && chmod +x /usr/local/bin/entrypoint.sh

# Bake the models into the image so the first request is instant.
RUN python scripts/download_models.py

# Run as a normal user. The data directory is the only writable path.
RUN useradd --create-home --uid 10001 fieldnote \
    && mkdir -p /app/data \
    && chown -R fieldnote:fieldnote /app
USER fieldnote

EXPOSE 8000
VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=600s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["fieldnote", "serve", "--host", "0.0.0.0", "--port", "8000"]
