FROM node:24-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM debian:bookworm-slim AS engine-assets
ARG TARGETARCH
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
RUN set -eu; \
    case "${TARGETARCH}" in \
      amd64) arch=x86-64; digest=9defc0d4e55d49c65a6d042f3e571a39fcea499ade6dbe741b53b8c65e03611f ;; \
      arm64) arch=arm64; digest=fe26cfd1d9db4c8af3d21e24d9ff34cacb31c1f940085a7583da11796f2bac01 ;; \
      *) echo "Unsupported Stockfish architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    name="stockfish-linux-${arch}-universal"; \
    mkdir -p /assets /tmp/stockfish; \
    curl --fail --location --retry 3 "https://github.com/official-stockfish/Stockfish/releases/download/sf_19/${name}.tar.gz" --output /tmp/stockfish.tar.gz; \
    printf '%s  %s\n' "$digest" /tmp/stockfish.tar.gz | sha256sum --check; \
    tar -xzf /tmp/stockfish.tar.gz -C /tmp/stockfish; \
    install -m 0755 "/tmp/stockfish/stockfish/$name" /assets/stockfish; \
    install -m 0644 /tmp/stockfish/stockfish/Copying.txt /assets/stockfish-license.txt; \
    rm -rf /tmp/stockfish /tmp/stockfish.tar.gz

RUN curl --fail --location --retry 3 \
    'https://huggingface.co/UofTCSSLab/Maia3-5M/resolve/b6559de2398d7140b985f28fd2c19fb5e47ddabe/maia3-5m.pt' \
    --output /assets/maia3-5m.pt \
    && printf '%s  %s\n' ba14208b2992d85502f5fb501934abf6aaaeb355e9f3fdf90e326911f562524f /assets/maia3-5m.pt | sha256sum --check

FROM python:3.12-slim-bookworm
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=10000 \
    STOCKFISH_PATH=/usr/local/bin/stockfish \
    STOCKFISH_THREADS=1 \
    STOCKFISH_HASH_MB=16 \
    MAIA3_PATH=/usr/local/bin/python \
    MAIA3_ARGS="scripts/maia3_uci.py --model maia3-5m --checkpoint-path /app/models/maia3-5m.pt --use-uci-history --device cpu --no-use-amp --local-files-only" \
    MAIA_THREADS=1 \
    MAIA_START_TIMEOUT=50 \
    HF_HUB_OFFLINE=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MALLOC_ARENA_MAX=2

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin humangm \
    && install -d -o humangm -g humangm /app/data

COPY requirements-render.txt ./
RUN python -m pip install --index-url https://download.pytorch.org/whl/cpu 'torch==2.15.0+cpu' \
    && python -m pip install -r requirements-render.txt

COPY --from=engine-assets /assets/stockfish /usr/local/bin/stockfish
COPY --from=engine-assets /assets/stockfish-license.txt /app/licenses/stockfish.txt
COPY --from=engine-assets /assets/maia3-5m.pt /app/models/maia3-5m.pt
COPY backend/ /app/backend/
COPY config/ /app/config/
COPY scripts/maia3_uci.py scripts/cache_maia3.py /app/scripts/
COPY vendor/maia3/maia3/ /app/vendor/maia3/maia3/
COPY vendor/maia3/LICENSE vendor/maia3/README.md vendor/maia3/pyproject.toml /app/vendor/maia3/
COPY --from=frontend /build/dist/ /app/frontend/dist/
RUN mkdir -p /app/frontend/dist/downloads \
    && tar -czf /app/frontend/dist/downloads/maia3-uci-source.tar.gz \
       scripts/maia3_uci.py scripts/cache_maia3.py vendor/maia3

USER humangm
EXPOSE 10000
CMD ["sh", "-c", "exec python -m uvicorn backend.main:app --host 0.0.0.0 --port \"${PORT}\""]
