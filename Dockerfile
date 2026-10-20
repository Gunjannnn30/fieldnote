# Fieldnote - CPU-only image, no GPU required.
#
#   docker build -t fieldnote .
#   docker run -p 8000:8000 fieldnote
#
# The corpus is built and indexed on first start, then cached in the volume.

FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_DISABLE_SYMLINKS_WARNING=1 \
    TOKENIZERS_PARALLELISM=false \
    OMP_NUM_THREADS=4

WORKDIR /app

# Build deps for the wheels that need them, then get rid of them again.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# CPU-only torch keeps the image roughly 2 GB smaller than the CUDA build.
RUN pip install --no-cache-dir \
    torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu

COPY pyproject.toml README.md ./
COPY fieldnote ./fieldnote
COPY scripts ./scripts

RUN pip install --no-cache-dir . && \
    apt-get purge -y build-essential && apt-get autoremove -y

# Models live in the image so the first request is not a 2 GB download.
RUN python scripts/download_models.py

EXPOSE 8000
VOLUME ["/app/data"]

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["fieldnote", "serve", "--host", "0.0.0.0", "--port", "8000"]
