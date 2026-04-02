# syntax=docker/dockerfile:1.5
FROM --platform=linux/amd64 python:3.14-trixie AS builder

LABEL maintainer="Front Matter <info@front-matter.de>"
LABEL org.opencontainers.image.source="https://github.com/front-matter/rogue-scholar-api"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.title="Rogue Scholar API"
LABEL org.opencontainers.image.description="Rogue Scholar API is an API for the Rogue Scholar science blog archive."


# Install OS package dependency: pandoc
ENV PANDOC_VERSION=3.9.0.2 \
    VIRTUAL_ENV=/opt/venv \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

ADD https://github.com/jgm/pandoc/releases/download/${PANDOC_VERSION}/pandoc-${PANDOC_VERSION}-1-amd64.deb /tmp/pandoc.deb

# install uv to manage Python dependencie
# Explicitly set the virtual environment used by uv
COPY --from=ghcr.io/astral-sh/uv:0.10.10 /uv /uvx /bin/

RUN dpkg -i /tmp/pandoc.deb && \
    uv venv ${VIRTUAL_ENV}

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN touch README.md
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

FROM --platform=linux/amd64 python:3.14-slim-trixie AS runtime

# Install OS package dependency (for weasyprint): pango
RUN --mount=type=cache,target=/var/cache/apt apt-get update -y && \
    apt-get install \
    pango1.0-tools \
    libpq5 \
    -y --no-install-recommends && \
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
EXPOSE 5200

CMD ["hypercorn", "-b",  "0.0.0.0:5200", "api:app"]
