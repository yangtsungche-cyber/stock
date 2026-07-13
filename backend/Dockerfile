FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Cloud Run injects $PORT (defaults to 8080) and expects the container to listen on it.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
