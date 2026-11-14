FROM node:22.17-alpine AS frontend-build
WORKDIR /workspace/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace/backend \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH

WORKDIR /workspace

COPY backend/pyproject.toml backend/uv.lock /workspace/backend/
RUN uv sync --project /workspace/backend --locked --no-dev --no-install-project --python 3.11

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid 10001 --home-dir /nonexistent \
       --shell /usr/sbin/nologin app \
    && mkdir -p /workspace/releases/atlas30 \
    && chown 10001:10001 /workspace/releases/atlas30

COPY backend/app/ /workspace/backend/app/
COPY data/regions.json /workspace/data/regions.json
COPY docs/ /workspace/docs/
COPY specs/ /workspace/specs/
COPY scripts/ /workspace/scripts/
COPY requirements-minerales.txt /workspace/requirements-minerales.txt
COPY --from=frontend-build /workspace/frontend/dist/ /workspace/frontend/dist/

USER 10001:10001
WORKDIR /workspace/backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/openapi.json', timeout=3)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
