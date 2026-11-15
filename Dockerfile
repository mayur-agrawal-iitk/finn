# FINN live engine: the PWA + on-demand research for any NSE symbol.
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 FINN_CACHE=/tmp/finn-cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY finn ./finn
COPY prompts ./prompts
COPY data ./data
COPY web ./web
EXPOSE 8000
# ANTHROPIC_API_KEY is optional: without it, model steps are served from the committed cache.
CMD ["sh", "-c", "uvicorn finn.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
