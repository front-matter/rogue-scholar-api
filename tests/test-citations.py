"""Test citations."""

import pytest  # noqa: F401
import pydash as py_  # noqa: F401

from api.citations import extract_all_citations


@pytest.mark.asyncio
async def test_extract_all_citations_by_prefix():
    """Extract all citations by prefix."""
    slug = "10.54900"
    result = await extract_all_citations(slug)
    assert len(result) == 7
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
    result = await extract_all_citations(slug)
    assert len(result) == 1
    citation = result[0]
    assert citation["cid"] == "10.59350/ffgmk-zjj78::10.53731/2vcn2-qq962"
    assert citation["doi"] == "https://doi.org/10.59350/ffgmk-zjj78"
    assert citation["citation"] == "https://doi.org/10.53731/2vcn2-qq962"
    assert (
        citation["unstructured"]
        == "Fenner, M. (2025). Rogue Scholar Newsletter January 2025. In <i>Front Matter</i>. https://doi.org/10.53731/2vcn2-qq962"
    )
    assert citation["published_at"] == "2025-01-30"
