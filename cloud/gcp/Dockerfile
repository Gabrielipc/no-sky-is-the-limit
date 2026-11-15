FROM ghcr.io/prefix-dev/pixi:0.41.4-jammy

WORKDIR /app

# Install system tools needed for cloud sync and git checkouts
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency manifests first for layer caching
COPY pixi.toml pixi.lock* requirements-minerales.txt ./

# Install conda-forge + pip dependencies defined in pixi.toml
RUN pixi install --locked || pixi install

# Copy pipeline source (data/raw is excluded via .dockerignore)
COPY pipelines ./pipelines
COPY scripts ./scripts
COPY backend ./backend
COPY specs ./specs

# Install analysis-only pip dependencies (h5py) using the repository venv helper
RUN bash scripts/preparar_minerales.sh

# Verify planetary CRS definitions (Mars & Moon IAU_2015)
RUN pixi run check-env

ENV ATLAS_CACHE_DIR=/tmp/atlas30_cache \
    ANALOGOS_FEATURE_STORE_DIR=/app/data/feature_store_v1

ENTRYPOINT ["bash", "scripts/ejecutar_minerales.sh"]
CMD ["scripts/etl_pipeline.py", "--help"]
