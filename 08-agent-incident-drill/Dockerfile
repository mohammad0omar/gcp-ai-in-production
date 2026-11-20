FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
# Pin uv. Install exactly what uv.lock says, so the image matches the tests.
COPY --from=ghcr.io/astral-sh/uv:0.11.24 /uv /usr/local/bin/uv
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY config.py main.py ./
COPY agents ./agents

# Run as a non-root user.
RUN useradd --create-home appuser
USER appuser

# Tracing content stays off. The README sets this on Cloud Run too.
ENV ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false PATH="/app/.venv/bin:$PATH"

# python -m puts the working directory on the path, so `import config` works.
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
