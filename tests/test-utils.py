"""Test utils"""
import pytest  # noqa: F401

from rogue_scholar_api.utils import get_doi_metadata_from_ra


def test_get_doi_metadata_bibtex():
    "get doi metadata in bibtex format"
    doi = "https://doi.org/10.53731/ybhah-9jy85"
    result = get_doi_metadata_from_ra(doi)
    assert (
        result["data"]
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
    result = get_doi_metadata_from_ra(doi, format_="citation")
    assert (
        result["data"]
        == "Fenner, M. (2023). The rise of the (science) newsletter. https://doi.org/10.53731/ybhah-9jy85"
    )


# def test_sanitize_cool_suffix():
#     "sanitize cool suffix"
#     suffix = "sfzv4-xdb68"
#     sanitized_suffix = sanitize_suffix(suffix)
#     assert sanitized_suffix == "sfzv4-xdb68"


# def test_sanitize_semantic_suffix():
#     "sanitize semantic suffix"
#     suffix = "dini-blog.20230724"
#     sanitized_suffix = sanitize_suffix(suffix)
#     assert sanitized_suffix == "dini-blog.20230724"


# def test_sanitize_sici_suffix():
#     "sanitize sici suffix"
#     suffix = "0002-8231(199412)45:10<737:TIODIM>2.3.TX;2-M"
#     sanitized_suffix = sanitize_suffix(suffix)
#     assert sanitized_suffix == "0002-8231(199412)45:10<737:TIODIM>2.3.TX;2-M"


# def test_sanitize_invalid_suffix():
#     "sanitize invalid suffix"
#     suffix = "000 333"
#     sanitized_suffix = sanitize_suffix(suffix)
#     assert sanitized_suffix == "0002-8231(199412)45:10<737:TIODIM>2.3.TX;2-M"
