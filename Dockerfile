# Dockerfile that builds the Rogue Scholar API Docker image.
# Based on https://medium.com/@albertazzir/blazing-fast-python-docker-builds-with-poetry-a78a66f5aed0
ARG BUILDPLATFORM=linux/amd64
FROM --platform=$BUILDPLATFORM python:3.12-bookworm as builder

ENV POETRY_VERSION=1.8.2

RUN pip install poetry==${POETRY_VERSION} 

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN touch README.md
RUN --mount=type=cache,target=$POETRY_CACHE_DIR poetry install --without dev --no-root


FROM --platform=$BUILDPLATFORM python:3.12-slim-bookworm as runtime

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PANDOC_VERSION=3.1.12.3

COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

# Update installed APT packages
RUN apt-get update && apt-get upgrade -y && \
    apt-get install wget weasyprint -y && \
    wget -q https://github.com/jgm/pandoc/releases/download/${PANDOC_VERSION}/pandoc-${PANDOC_VERSION}-1-amd64.deb && \
    dpkg -i pandoc-${PANDOC_VERSION}-1-amd64.deb && \
    apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

WORKDIR /app
COPY api ./api
COPY pandoc ./pandoc
COPY hypercorn.toml ./
EXPOSE 8080

CMD ["hypercorn", "-b",  "0.0.0.0:8080", "api:app"]
