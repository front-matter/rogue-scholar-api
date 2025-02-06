# syntax=docker/dockerfile:1.5
ARG BUILDPLATFORM=linux/amd64
FROM --platform=$BUILDPLATFORM python:3.12-bookworm AS builder

# Dockerfile that builds the Rogue Scholar API Docker image. Based on the following:
# - https://medium.com/@albertazzir/blazing-fast-python-docker-builds-with-poetry-a78a66f5aed0
# - https://pythonspeed.com/articles/smaller-python-docker-images/
# - https://pythonspeed.com/articles/multi-stage-docker-python/

# Install OS package dependency: pandoc
ENV PANDOC_VERSION=3.4 \
    VIRTUAL_ENV=/opt/venv \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

ADD https://github.com/jgm/pandoc/releases/download/${PANDOC_VERSION}/pandoc-${PANDOC_VERSION}-1-amd64.deb /tmp/pandoc-${PANDOC_VERSION}-1-amd64.deb

# install uv to manage Python dependencie
# Explicitly set the virtual environment used by uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN dpkg -i /tmp/pandoc-${PANDOC_VERSION}-1-amd64.deb && \
    uv venv ${VIRTUAL_ENV}

WORKDIR /app

COPY pyproject.toml ./
RUN touch README.md
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip compile pyproject.toml -o requirements.txt && \
    uv pip install -r requirements.txt

FROM --platform=$BUILDPLATFORM python:3.12-slim-bookworm AS runtime

# Install OS package dependency (for weasyprint): pango
RUN --mount=type=cache,target=/var/cache/apt apt-get update -y && \
    apt-get install pango1.0-tools=1.50.12+ds-1 -y --no-install-recommends && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV VIRTUAL_ENV=/opt/venv \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

# Copy pandoc binary
COPY --from=builder /usr/bin/pandoc /usr/bin/pandoc

COPY api ./api
COPY pandoc ./pandoc
COPY hypercorn.toml ./
EXPOSE 8080

CMD ["hypercorn", "-b",  "0.0.0.0:8080", "api:app"]
