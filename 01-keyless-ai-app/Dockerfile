FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /srv

COPY app/requirements.txt app/requirements.txt
RUN pip install --no-cache-dir -r app/requirements.txt

COPY config.py .
COPY app app

RUN useradd --system --no-create-home appuser
USER appuser

# Cloud Run sets $PORT.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8080}\""]
