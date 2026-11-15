FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace/backend \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH

WORKDIR /workspace

COPY backend/pyproject.toml backend/uv.lock /workspace/backend/
RUN uv sync --project /workspace/backend --locked --no-dev --no-install-project --python 3.11

COPY backend/app/ /workspace/backend/app/
COPY data/regions.json /workspace/data/regions.json
COPY docs/ /workspace/docs/
COPY specs/ /workspace/specs/
COPY scripts/ /workspace/scripts/
COPY requirements-minerales.txt /workspace/requirements-minerales.txt

WORKDIR /workspace/backend
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
