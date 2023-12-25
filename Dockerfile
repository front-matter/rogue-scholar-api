# Based on https://dev.to/farcellier/package-a-poetry-project-in-a-docker-container-for-production-3b4m
# and https://stackoverflow.com/questions/53835198/integrating-python-poetry-with-docker
ARG BUILDPLATFORM=linux/amd64
FROM --platform=$BUILDPLATFORM python:3.11-slim-bookworm AS base

ENV PANDOC_VERSION=3.1.11
ENV POETRY_VERSION=1.7.1

# Update installed APT packages
RUN apt-get update && apt-get upgrade -y && \
    apt-get install wget nano tmux tzdata -y && \
    wget -q https://github.com/jgm/pandoc/releases/download/${PANDOC_VERSION}/pandoc-${PANDOC_VERSION}-1-amd64.deb && \
    dpkg -i pandoc-${PANDOC_VERSION}-1-amd64.deb && \
    apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN pip install --no-cache-dir poetry==${POETRY_VERSION} 
COPY . /.

# WORKDIR /app

ENV PATH .venv/bin:$PATH

RUN poetry install --without dev

EXPOSE 8080

# CMD ["hypercorn", "-b", "0.0.0.0:5000", "api:app"]
CMD ["poetry", "run", "hypercorn", "-b",  "0.0.0.0:8080", "api:app"]
