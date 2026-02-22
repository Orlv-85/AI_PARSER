ARG PYTHON_IMAGE=python:3.14-slim

FROM ${PYTHON_IMAGE} AS base

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

COPY build/requirements.txt ./build/requirements.txt
COPY build/requirements-dev.txt ./build/requirements-dev.txt
COPY pyproject.toml README.md alembic.ini ./
COPY src ./src
COPY sources.yaml ./sources.yaml
COPY scripts ./scripts
COPY run_web.sh ./run_web.sh

FROM base AS runtime

RUN pip install --upgrade pip \
    && pip install -r ./build/requirements.txt \
    && pip install --no-deps .

RUN mkdir -p /app/data

EXPOSE 8010

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import sys,urllib.request;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8010/health', timeout=3).status == 200 else 1)"

CMD ["ai-news", "serve", "--host", "0.0.0.0", "--port", "8010"]

FROM base AS test

COPY tests ./tests

RUN pip install --upgrade pip \
    && pip install -r ./build/requirements-dev.txt \
    && pip install --no-deps -e .

CMD ["./scripts/run_tests_with_coverage.sh"]

FROM runtime AS final
