FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    AINEWS_DATABASE_URL=sqlite:///./data/ai_news.db \
    AINEWS_SOURCES_PATH=/app/sources.yaml

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md alembic.ini ./
COPY src ./src
COPY sources.yaml ./sources.yaml
COPY scripts ./scripts
COPY run_web.sh ./run_web.sh

RUN pip install .

RUN mkdir -p /app/data

EXPOSE 8010

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import sys,urllib.request;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8010/health', timeout=3).status == 200 else 1)"

CMD ["ai-news", "serve", "--host", "0.0.0.0", "--port", "8010"]
