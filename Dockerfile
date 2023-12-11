# The builder image, used to build the virtual environment
FROM python:3.11-bookworm AS builder

RUN pip install poetry==1.7.1

ENV POETRY_NO_INTERACTION=1 \
  POETRY_VIRTUALENVS_IN_PROJECT=1 \
  POETRY_VIRTUALENVS_CREATE=1 \
  POETRY_CACHE_DIR=/tmp/poetry_cache

WORKDIR /rogue_scholar_api

COPY pyproject.toml poetry.lock ./
RUN touch README.md

RUN poetry install --without dev --no-root && rm -rf $POETRY_CACHE_DIR

# The runtime image, used to just run the code provided its virtual environment
FROM python:3.11-slim-bookworm AS runtime

ENV VIRTUAL_ENV=/rogue_scholar_api/.venv \
  PATH="/rogue_scholar_api/.venv/bin:$PATH"

COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

COPY rogue_scholar_api ./rogue_scholar_api

CMD ["hypercorn", "-b", "0.0.0.0:$PORT", "rogue_scholar_api:app"]