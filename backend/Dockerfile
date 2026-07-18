FROM python:3.12-slim

WORKDIR /app

# WeasyPrint (PDF report export, app/services/report.py) needs Pango/Cairo/GDK-Pixbuf at
# runtime, plus a CJK-capable font — without fonts-noto-cjk every Traditional Chinese
# character in the generated PDF renders as an empty box.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf2.0-0 libffi-dev \
    shared-mime-info fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Cloud Run injects $PORT (defaults to 8080) and expects the container to listen on it.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
