"""Test utils"""
import pytest  # noqa: F401

from rogue_scholar_api.utils import get_doi_metadata_from_ra


def test_get_doi_metadata_bibtex():
    "get doi metadata in bibtex format"
    doi = "https://doi.org/10.53731/ybhah-9jy85"
    headers = {"Accept": "application/x-bibtex"}
    bibtex = get_doi_metadata_from_ra(doi, headers=headers)
    assert (
        bibtex
        == """@article{Fenner_2023,
\tdoi = {10.53731/ybhah-9jy85},
\turl = {https://doi.org/10.53731%2Fybhah-9jy85},
\tyear = 2023,
\tmonth = {oct},
\tpublisher = {Front Matter},
\tauthor = {Martin Fenner},
\ttitle = {The rise of the (science) newsletter}
}"""
    )


def test_get_doi_metadata_citation():
    "get doi metadata as formatted citation"
    doi = "https://doi.org/10.53731/ybhah-9jy85"
    headers = {"Accept": "text/x-bibliography; style=apa"}
    citation = get_doi_metadata_from_ra(doi, headers=headers)
    assert (
        citation
        == "Fenner, M. (2023). The rise of the (science) newsletter. https://doi.org/10.53731/ybhah-9jy85"
    )
