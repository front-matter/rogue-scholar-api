# syntax=docker/dockerfile:1.5
ARG BUILDPLATFORM=linux/amd64
FROM --platform=$BUILDPLATFORM python:3.12-bookworm AS builder

# Dockerfile that builds the Rogue Scholar API Docker image. Based on the following:
# - https://medium.com/@albertazzir/blazing-fast-python-docker-builds-with-poetry-a78a66f5aed0
# - https://pythonspeed.com/articles/smaller-python-docker-images/
# - https://pythonspeed.com/articles/multi-stage-docker-python/
# - https://stackoverflow.com/questions/53835198/integrating-python-poetry-with-docker

# Install OS package dependency: pandoc
# install poetry to manage Python dependencies
ENV PANDOC_VERSION=3.1.12.3 \
    POETRY_VERSION=1.8.3

ADD https://github.com/jgm/pandoc/releases/download/${PANDOC_VERSION}/pandoc-${PANDOC_VERSION}-1-amd64.deb /tmp/pandoc-${PANDOC_VERSION}-1-amd64.deb

RUN dpkg -i /tmp/pandoc-${PANDOC_VERSION}-1-amd64.deb && \
    pip install --no-cache-dir poetry==${POETRY_VERSION}

# Explicitly set the virtual environment used by Poetry
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Install Python dependencies using Poetry
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=0 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN touch README.md
RUN --mount=type=cache,target=$POETRY_CACHE_DIR poetry install --without dev --no-root --no-interaction --no-ansi


FROM --platform=$BUILDPLATFORM python:3.12-slim-bookworm AS runtime

# Install OS package dependency (for weasyprint): pango
RUN --mount=type=cache,target=/var/cache/apt apt-get update -y && \
    apt-get install pango1.0-tools=1.50.12+ds-1 -y --no-install-recommends && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

# Copy pandoc binary
COPY --from=builder /usr/bin/pandoc /usr/bin/pandoc

COPY api ./api
COPY pandoc ./pandoc
COPY hypercorn.toml ./
EXPOSE 8080

CMD ["hypercorn", "-b",  "0.0.0.0:8080", "api:app"]
