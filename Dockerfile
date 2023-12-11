# The builder image, used to build the virtual environment
# from https://stackoverflow.com/questions/72465421/how-to-use-poetry-with-docker
FROM python:3.11-bookworm AS builder

# Configure Poetry
ENV POETRY_VERSION=1.7.1
ENV POETRY_HOME=/opt/poetry
ENV POETRY_VENV=/opt/poetry-venv

# Tell Poetry where to place its cache and virtual environment
ENV POETRY_CACHE_DIR=/opt/.cache

# Create stage for Poetry installation
FROM builder AS poetry-base

# Creating a virtual environment just for poetry and install it with pip
RUN python3 -m venv ${POETRY_VENV} \
    && ${POETRY_VENV}/bin/pip install -U pip setuptools \
    && ${POETRY_VENV}/bin/pip install poetry==${POETRY_VERSION}

# Create a new stage from the base python image
FROM builder AS example-app

# Copy Poetry to app image
COPY --from=poetry-base ${POETRY_VENV} ${POETRY_VENV}

# Add Poetry to PATH
ENV PATH="${PATH}:${POETRY_VENV}/bin"

WORKDIR /app

# Copy Dependencies
COPY poetry.lock pyproject.toml ./

# [OPTIONAL] Validate the project is properly configured
RUN poetry check

# Install Dependencies
RUN poetry install --no-interaction --no-cache --without dev

# Copy Application
COPY . /app

# Run Application
EXPOSE $PORT
CMD [ "poetry", "run", "python", "-m", "flask", "run", "--host=0.0.0.0" ]
