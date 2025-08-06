"""Test citations."""

import pytest  # noqa: F401
import pydash as py_  # noqa: F401

from api.citations import extract_all_citations_by_prefix


@pytest.mark.asyncio
async def test_extract_all_citations_by_prefix():
    """Extract all citations by prefix."""
    slug = "10.54900"
    result = await extract_all_citations_by_prefix(slug)
    assert len(result) == 14
    citation = result[0]
    assert citation["cid"] == "10.59350/4rj2q-98c96::10.3233/jnr-220002"
    assert citation["doi"] == "https://doi.org/10.59350/4rj2q-98c96"
    assert citation["citation"] == "https://doi.org/10.3233/jnr-220002"
    assert (
        citation["unstructured"]
        == "Wuttke, J., Cottrell, S., Gonzalez, M. A., Kaestner, A., Markvardsen, A., Rod, T. H., Rozyczko, P., &amp; Vardanyan, G. (2022). Guidelines for collaborative development of sustainable data treatment software. <i>Journal of Neutron Research</i>, <i>24</i>(1), 33–72. https://doi.org/10.3233/jnr-220002"
    )
    assert citation["published_at"] == "2022-03-22"


@pytest.mark.asyncio
async def test_extract_all_citations_by_doi():
    """Extract all citations by doi."""
    slug = "10.59350/ffgmk-zjj78"
    result = await extract_all_citations_by_prefix(slug)
    assert len(result) == 2
    citation = result[0]
    assert citation["cid"] == "10.59350/ffgmk-zjj78::10.53731/4bvt3-hmd07"
    assert citation["doi"] == "https://doi.org/10.59350/ffgmk-zjj78"
    assert citation["citation"] == "https://doi.org/10.53731/4bvt3-hmd07"
    assert (
        citation["unstructured"]
        == "Fenner, M. (2025, February 3). Rogue Scholar now shows citations of science blog posts. <i>Front Matter</i>. https://doi.org/10.53731/4bvt3-hmd07"
    )
    assert citation["published_at"] == "2025-02-03"
