"""Test utils"""
import pytest  # noqa: F401
import pydash as py_  # noqa: F401
import json

from api.utils import (
    get_date,
    get_doi_metadata_from_ra,
    validate_uuid,
    unix_timestamp,
    end_of_date,
    start_case,
    normalize_tag,
    detect_language,
    normalize_author,
    normalize_url,
    get_markdown,
)


def test_get_date_rss():
    "parse datetime from rss"
    date = "Mon, 18 Sep 2023 04:00:00 GMT"
    result = get_date(date)
    assert result == "2023-09-18T04:00:00+00:00"


def test_get_doi_metadata_bibtex():
    "get doi metadata in bibtex format"
    doi = "https://doi.org/10.53731/ybhah-9jy85"
    result = get_doi_metadata_from_ra(doi, format_="bibtex")
    assert (
        result["data"]
        == """@article{Fenner_2023,
\ttitle = {The rise of the (science) newsletter},
\turl = {http://dx.doi.org/10.53731/ybhah-9jy85},
\tDOI = {10.53731/ybhah-9jy85},
\tpublisher = {Front Matter},
\tauthor = {Fenner, Martin},
\tyear = {2023},
\tmonth = {oct}
}"""
    )


def test_get_doi_metadata_csl():
    "get doi metadata in csl format"
    doi = "https://doi.org/10.59350/e3wmw-qwx29"
    result = get_doi_metadata_from_ra(doi, format_="csl")
    csl = json.loads(result["data"])
    print(csl)
    assert (
        csl["title"]
        == "Two influential textbooks &#8211; &#8220;Mee&#8221;  and &#8220;Mellor&#8221;."
    )


def test_get_doi_metadata_citation():
    "get doi metadata as formatted citation"
    doi = "https://doi.org/10.53731/ybhah-9jy85"
    result = get_doi_metadata_from_ra(doi, format_="citation")
    assert (
        result["data"]
        == "Fenner, M. (2023). The rise of the (science) newsletter. https://doi.org/10.53731/ybhah-9jy85"
    )


def test_validate_uuid():
    "validate uuid"
    uuid = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
    result = validate_uuid(uuid)
    assert result is True


def test_validate_invalid_uuid_():
    "validate invalid uuid"
    uuid = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a1"
    result = validate_uuid(uuid)
    assert result is False


def test_unix_timestamp():
    "convert iso8601 date to unix timestamp"
    date = "2021-08-01"
    assert unix_timestamp(date) == 1627776000


def test_unix_timestamp_year_month():
    "convert iso8601 date to unix timestamp"
    date = "2021-08"
    assert unix_timestamp(date) == 1627776000


def test_unix_timestamp_year():
    "convert iso8601 date to unix timestamp"
    date = "2021"
    assert unix_timestamp(date) == 1609459200


def test_end_of_day_day():
    """convert iso8601 date to end of day"""
    date = "2021-08-01"
    assert end_of_date(date) == "2021-08-01T23:59:59+00:00"


def test_end_of_day_month():
    """convert iso8601 date to end of month"""
    date = "2021-09"
    assert end_of_date(date) == "2021-09-30T23:59:59+00:00"


def test_end_of_day_year():
    """convert iso8601 date to end of year"""
    date = "2021"
    assert end_of_date(date) == "2021-12-31T23:59:59+00:00"


def test_start_case():
    """capitalize first letter without lowercasing the rest"""
    content = "wikiCite"
    assert start_case(content) == "WikiCite"


def test_normalize_tag():
    """normalize tag"""
    tag = "#open science"
    assert normalize_tag(tag) == "Open Science"


def test_normalize_tag_fixed():
    """normalize tag fixed"""
    tag = "#OSTP"
    assert normalize_tag(tag) == "OSTP"


def test_detect_language_english():
    """detect language english"""
    text = "This is a test"
    assert detect_language(text) == "en"


def test_detect_language_german():
    """detect language german"""
    text = "Dies ist ein Test"
    assert detect_language(text) == "de"


def test_detect_language_french():
    """detect language french"""
    text = "Ceci est un test"
    assert detect_language(text) == "fr"


def test_detect_language_spanish():
    """detect language spanish"""
    text = "Esto es una prueba"
    assert detect_language(text) == "es"


def test_normalize_author_username():
    """normalize author username"""
    name = "davidshotton"
    result = normalize_author(name)
    assert result == {
        "name": "David M. Shotton",
        "url": "https://orcid.org/0000-0001-5506-523X",
    }


def test_normalize_author_suffix():
    """normalize author suffix"""
    name = "Tejas S. Sathe, MD"
    result = normalize_author(name)
    assert result == {
        "name": "Tejas S. Sathe",
        "url": "https://orcid.org/0000-0003-0449-4469",
    }


def test_normalize_author_gpt4():
    """normalize author GPT-4"""
    name = "GPT-4"
    result = normalize_author(name)
    assert result == {
        "name": "Tejas S. Sathe",
        "url": "https://orcid.org/0000-0003-0449-4469",
    }


def test_normalize_url_slash():
    """normalize url with slash"""
    url = "https://www.example.com/"
    result = normalize_url(url)
    assert result == "https://www.example.com"


def test_normalize_url_with_index():
    """normalize url with index_html"""
    url = "https://www.example.com/index.html"
    result = normalize_url(url)
    assert result == "https://www.example.com"


def test_normalize_url_with_utm_params():
    """normalize url with utm params"""
    url = "https://www.example.com?utm_source=example.com&utm_medium=referral&utm_campaign=example.com"
    result = normalize_url(url)
    assert result == "https://www.example.com"


def test_normalize_url_with_slash_param():
    """normalize url with slash param"""
    url = "https://www.ch.imperial.ac.uk/rzepa/blog/?p=25304"
    result = normalize_url(url)
    assert result == "https://www.ch.imperial.ac.uk/rzepa/blog?p=25304"


def test_get_markdown():
    """get markdown from html"""
    html = "<p>This is a <em>test</em></p>"
    result = get_markdown(html)
    assert result == "This is a *test*\n"
    
    
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
