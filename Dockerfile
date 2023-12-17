# Based on https://dev.to/farcellier/package-a-poetry-project-in-a-docker-container-for-production-3b4m
# and https://stackoverflow.com/questions/53835198/integrating-python-poetry-with-docker
FROM python:3.11-slim-bookworm AS base

RUN pip install --no-cache-dir poetry==1.7.1 && \
    mkdir -p /app  
COPY . /app

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH"

RUN poetry install --without dev

# Run Application
EXPOSE 5000

CMD ["poetry", "run", "start"]
