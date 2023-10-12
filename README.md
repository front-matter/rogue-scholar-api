[![Build](https://github.com/front-matter/rogue-scholar-api/actions/workflows/build.yml/badge.svg)](https://github.com/front-matter/rogue-scholar-api/actions/workflows/build.yml)
[![PyPI version](https://img.shields.io/pypi/v/rogue-scholar-api.svg)](https://pypi.org/project/rogue-scholar-api/)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=front-matter_rogue-scholar-api&metric=coverage)](https://sonarcloud.io/summary/new_code?id=front-matter_rogue-scholar-api)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=front-matter_rogue-scholar-api&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=front-matter_rogue-scholar-api)
[![docs](https://img.shields.io/badge/docs-passing-blue)](https://docs.rogue-scholar.org)
![GitHub](https://img.shields.io/github/license/front-matter/rogue-scholar-api?logo=MIT)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.8433679.svg)](https://doi.org/10.5281/zenodo.8433679)

# Rogue Scholar API

The backend server for the [Rogue Scholar](https://rogue-scholar.org) science blog archive. The Rogue Scholar API is a Python [Quart](https://pgjones.gitlab.io/quart/) application that provides a RESTful API for the Rogue Scholar service.

## Installation

Requires Python 3.8 or higher (Python 3.11 recommended). Uses [Poetry](https://python-poetry.org/) for dependency management. Depends on credentials for the Rogue Scholar Postgres database (hosted by Supabase) and Rogue Scholar search index (hosted by Typesense):

```
# required environment variables
SUPABASE_URL
SUPABASE_ANON_KEY
TYPESENSE_HOST
TYPESENSE_API_KEY
```

The API uses Poetry for dependency management. To install Poetry, see the [Poetry documentation](https://python-poetry.org/docs/#installation). Then install the dependencies and run the server:

```
poetry install
poetry run quart --app rogue_scholar_api run
```

The API will then be available at `http://localhost:5000`.


## Development

We use pytest for testing:

```
poetry run pytest
```

Follow along via [Github Issues](https://github.com/front-matter/rogue-scholar-api/issues). Please open an issue if you encounter a bug or have a feature request.

### Note on Patches/Pull Requests

- Fork the project
- Write tests for your new feature or a test that reproduces a bug
- Implement your feature or make a bug fix
- Do not mess with Rakefile, version or history
- Commit, push and make a pull request. Bonus points for topical branches.

## Documentation

Documentation (work in progress) for using Rogue Scholar is available at the [Rogue Scholar Documentation](https://docs.rogue-scholar.org/) website.

The Rogue Scholar API documentation is served by default at [/openapi.json](https://api.rogue-scholar.org/openapi.json) according to the OpenAPI standard, or at [/docs](https://api.rogue-scholar.org/docs) for a SwaggerUI interface, or at [/redocs](https://api.rogue-scholar.org/redocs) for a redoc interface.

## Meta

Please note that this project is released with a [Contributor Code of Conduct](https://github.com/front-matter/rogue-scholar-api/blob/main/CODE_OF_CONDUCT.md). By participating in this project you agree to abide by its terms.  

License: [MIT](https://github.com/front-matter/rogue-scholar-api/blob/main/LICENSE)
