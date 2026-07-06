FROM python:3.13-slim AS base

RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv==0.9.2

CMD ["placeholder_override", "--allow-root"]

FROM base AS tester

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY tests/pyproject.toml .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev
ENV PATH="/.venv/bin:$PATH"

CMD ["pytest", "--broker_url=http://topology-broker.com:50051", "-s", "-vv"]

FROM base AS model
ARG MODEL_PATH

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=models/${MODEL_PATH}/pyproject.toml,target=pyproject.toml,readonly \
    uv sync --no-install-project --no-dev

COPY models/${MODEL_PATH}/ .

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev

ENV PATH="/.venv/bin:$PATH"

CMD ["placeholder_override", "--allow-root"]