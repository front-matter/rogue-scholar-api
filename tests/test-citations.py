"""Test citations."""

from os import environ

import pytest  # noqa: F401
import pydash as py_  # noqa: F401

from api import app


@pytest.mark.asyncio
async def test_extract_all_citations_by_prefix():
    """Extract all citations by prefix."""
    prefix = "10.54900"
    async with app.test_app():
        test_client = app.test_client()
        key = environ["ROGUE_SCHOLAR_SERVICE_ROLE_KEY"]
        headers = {"Authorization": f"Bearer {key}"}
        response = await test_client.post(f"/citations/{prefix}", headers=headers)
        assert response.status_code == 200
        result = await response.get_json()

    assert len(result) >= 1
    citation = py_.find(result, {"cid": "10.59350/4rj2q-98c96::10.3233/jnr-220002"})
    assert citation is not None
    assert citation["doi"] == "https://doi.org/10.59350/4rj2q-98c96"
    assert citation["citation"] == "https://doi.org/10.3233/jnr-220002"
    assert citation["published_at"] == "2022-03-22"


@pytest.mark.asyncio
async def test_extract_all_citations_by_doi():
    """Extract all citations by doi."""
    prefix = "10.59350"
    suffix = "ffgmk-zjj78"
    async with app.test_app():
        test_client = app.test_client()
        key = environ["ROGUE_SCHOLAR_SERVICE_ROLE_KEY"]
        headers = {"Authorization": f"Bearer {key}"}
        response = await test_client.post(
            f"/citations/{prefix}/{suffix}", headers=headers
        )
        assert response.status_code == 200
        result = await response.get_json()

    assert len(result) >= 1
    citation = py_.find(result, {"cid": "10.59350/ffgmk-zjj78::10.53731/4bvt3-hmd07"})
    assert citation is not None
    assert citation["doi"] == "https://doi.org/10.59350/ffgmk-zjj78"
    assert citation["citation"] == "https://doi.org/10.53731/4bvt3-hmd07"
    assert citation["published_at"] == "2025-02-03"
