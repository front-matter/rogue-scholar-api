# Dockerfile that builds the Rogue Scholar API Docker image.
# Based on https://medium.com/@albertazzir/blazing-fast-python-docker-builds-with-poetry-a78a66f5aed0
ARG BUILDPLATFORM=linux/amd64
FROM --platform=$BUILDPLATFORM python:3.12-bookworm as builder

ENV PANDOC_VERSION=3.1.12.3 \
    POETRY_VERSION=1.8.2

ADD https://github.com/jgm/pandoc/releases/download/${PANDOC_VERSION}/pandoc-${PANDOC_VERSION}-1-amd64.deb /tmp/pandoc-${PANDOC_VERSION}-1-amd64.deb
RUN dpkg -i /tmp/pandoc-${PANDOC_VERSION}-1-amd64.deb && \
    pip install --no-cache-dir poetry==${POETRY_VERSION} 

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN touch README.md && mkdir -p .venv
RUN --mount=type=cache,target=$POETRY_CACHE_DIR poetry install --without dev --no-root --no-interaction --no-ansi


FROM --platform=$BUILDPLATFORM python:3.12-slim-bookworm as runtime

RUN --mount=type=cache,target=/var/cache/apt apt-get update -y && \
    apt-get install libpango-1.0-0=1.50.12+ds-1 libpangoft2-1.0-0=1.50.12+ds-1 pango1.0-tools=1.50.12+ds-1 -y --no-install-recommends && \
    apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}
COPY --from=builder /usr/bin/pandoc /usr/bin/pandoc

WORKDIR /app
COPY api ./api
COPY pandoc ./pandoc
COPY hypercorn.toml ./
EXPOSE 8080

CMD ["hypercorn", "-b",  "0.0.0.0:8080", "api:app"]
