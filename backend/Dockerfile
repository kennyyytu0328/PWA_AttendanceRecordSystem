FROM python:3.13-slim

WORKDIR /app

# tzdata is required for the TZ env var (e.g. Asia/Taipei) to resolve — the
# slim image ships none, so without this glibc silently falls back to UTC and
# naive datetime.now() punches land 8 hours off.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
