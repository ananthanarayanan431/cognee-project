FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /debatemind-backend

# Install dependencies (layer-cached unless pyproject.toml changes)
COPY pyproject.toml .
RUN uv pip install --no-cache -r pyproject.toml

# Copy application source
COPY app/ debatemind/

EXPOSE 8000

CMD ["uvicorn", "debatemind.main:app", "--host", "0.0.0.0", "--port", "8000"]
