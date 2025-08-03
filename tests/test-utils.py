"""Test utils"""

import pytest  # noqa: F401
import pydash as py_  # noqa: F401
from os import path
import orjson as json
import frontmatter

from api.utils import (
    get_date,
    convert_to_commonmeta,
    get_formatted_metadata,
    validate_uuid,
    unix_timestamp,
    end_of_date,
    start_case,
    normalize_tag,
    detect_language,
    normalize_author,
    extract_atom_authors,
    normalize_url,
    get_markdown,
    write_epub,
    write_pdf,
    write_html,
    format_markdown,
    is_valid_url,
    id_as_str,
    get_single_work,
    format_reference,
    format_list_reference,
    extract_reference_id,
    get_soup,
    parse_blogger_guid,
    extract_wordpress_post_id,
)


def test_get_date_rss():
    "parse datetime from rss"
    date = "Mon, 18 Sep 2023 04:00:00 GMT"
    result = get_date(date)
    assert result == "2023-09-18T04:00:00+00:00"


def test_convert_to_commonmeta_default():
    """Concert metadata into commonmeta format"""
    string = path.join(path.dirname(__file__), "fixtures", "rogue-scholar.json")
    with open(string, encoding="utf-8") as file:
        string = file.read()
    data = json.loads(string)
    result = convert_to_commonmeta(data)
    assert result["id"] == "https://doi.org/10.59350/ps8tw-rpk77"
    assert result["schema_version"] == "https://commonmeta.org/commonmeta_v0.12"
    assert result["type"] == "BlogPost"
    assert result["url"] == "http://gigasciencejournal.com/blog/fair-workflows"
    assert py_.get(result, "titles.0") == {
        "title": "A Decade of FAIR – what happens next? Q&amp;A on FAIR workflows with the Netherlands X-omics Initiative"
    }
    assert len(result["contributors"]) == 1
    assert py_.get(result, "contributors.0") == {
        "type": "Person",
        "id": "https://orcid.org/0000-0001-6444-1436",
        "contributorRoles": ["Author"],
        "givenName": "Scott",
        "familyName": "Edmunds",
    }
    assert result["license"] == {
        "id": "CC-BY-4.0",
        "url": "https://creativecommons.org/licenses/by/4.0/legalcode",
    }

    assert result["date"] == {
        "published": "2024-01-13T19:10:51",
        "updated": "2024-01-13T19:10:51",
    }
    assert result["publisher"] == {"name": "GigaBlog"}
    assert len(result["references"]) == 0
    assert result["funding_references"] == []
    assert result["container"] == {"type": "Periodical", "title": "GigaBlog"}
    assert py_.get(result, "descriptions.0.description").startswith(
        "<em>\n Marking the 10\n <sup>\n  th\n </sup>\n anniversary"
    )
    assert result["subjects"] == [{"subject": "Biological sciences"}]
    assert result["provider"] == "Crossref"
    assert len(result["files"]) == 5
    assert py_.get(result, "files.2") == {
        "url": "https://api.rogue-scholar.org/posts/10.59350/ps8tw-rpk77.pdf",
        "mimeType": "application/pdf",
    }


def test_get_formatted_metadata_bibtex():
    "get formatted metadata in bibtex format"
    data = path.join(path.dirname(__file__), "fixtures", "commonmeta.json")
    result = get_formatted_metadata(data, format_="bibtex")
    assert (
        result["data"]
        == """@article{10.53731/ybhah-9jy85,
    abstract = {Newsletters have been around forever, but their popularity has significantly increased in the past few years, also thanks to platforms such as Ghost, Medium, and Substack. Which of course also includes science newsletters.Failure of advertising as a revenue model The most important driver of this trend is probably the realization that advertising is a poor revenue model for content published on the web, including blogs.},
    author = {Fenner, Martin},
    copyright = {https://creativecommons.org/licenses/by/4.0/legalcode},
    doi = {10.53731/ybhah-9jy85},
    month = oct,
    title = {The rise of the (science) newsletter},
    url = {https://blog.front-matter.io/posts/the-rise-of-the-science-newsletter},
    urldate = {2023-10-04},
    year = {2023}
}"""
    )


def test_get_url_metadata_bibtex():
    "get url metadata in bibtex format"
    data = path.join(path.dirname(__file__), "fixtures", "commonmeta-no-doi.json")
    result = get_formatted_metadata(data, format_="bibtex")
    assert (
        result["data"]
        == """@article{https://blog.front-matter.io/posts/the-rise-of-the-science-newsletter,
    abstract = {Newsletters have been around forever, but their popularity has significantly increased in the past few years, also thanks to platforms such as Ghost, Medium, and Substack. Which of course also includes science newsletters.Failure of advertising as a revenue model The most important driver of this trend is probably the realization that advertising is a poor revenue model for content published on the web, including blogs.},
    author = {Fenner, Martin},
    copyright = {https://creativecommons.org/licenses/by/4.0/legalcode},
    month = oct,
    title = {The rise of the (science) newsletter},
    url = {https://blog.front-matter.io/posts/the-rise-of-the-science-newsletter},
    urldate = {2023-10-04},
    year = {2023}
}"""
    )


def test_get_formatted_metadata_csl():
    "get formatted metadata in csl format"
    data = path.join(path.dirname(__file__), "fixtures", "commonmeta.json")
    result = get_formatted_metadata(data, format_="csl")
    csl = json.loads(result["data"])
    assert csl["title"] == "The rise of the (science) newsletter"
    assert csl["author"] == [{"family": "Fenner", "given": "Martin"}]


def test_get_url_metadata_csl():
    "get url metadata in csl format"
    data = path.join(path.dirname(__file__), "fixtures", "commonmeta-no-doi.json")
    result = get_formatted_metadata(data, format_="csl")
    csl = json.loads(result["data"])
    assert csl["title"] == "The rise of the (science) newsletter"
    assert csl["author"] == [{"family": "Fenner", "given": "Martin"}]
    assert (
        csl["URL"]
        == "https://blog.front-matter.io/posts/the-rise-of-the-science-newsletter"
    )


def test_get_formatted_metadata_ris():
    "get formatted metadata in ris format"
    data = path.join(path.dirname(__file__), "fixtures", "commonmeta.json")
    result = get_formatted_metadata(data, format_="ris")
    ris = result["data"].split("\r\n")
    assert ris[1] == "T1  - The rise of the (science) newsletter"
    assert ris[2] == "AU  - Fenner, Martin"


def test_get_formatted_metadata_commonmeta():
    "get formatted metadata in commonmeta format"
    data = path.join(path.dirname(__file__), "fixtures", "commonmeta.json")
    result = get_formatted_metadata(data)
    commonmeta = json.loads(result["data"])
    assert (
        commonmeta["titles"][0].get("title") == "The rise of the (science) newsletter"
    )
    assert commonmeta["contributors"] == [
        {
            "id": "https://orcid.org/0000-0003-1419-2405",
            "type": "Person",
            "contributorRoles": ["Author"],
            "givenName": "Martin",
            "familyName": "Fenner",
        }
    ]


def test_get_formatted_metadata_schema_org():
    "get doi metadata in schema_org format"
    data = path.join(path.dirname(__file__), "fixtures", "commonmeta.json")
    result = get_formatted_metadata(data, format_="schema_org")
    schema_org = json.loads(result["data"])
    assert schema_org["name"] == "The rise of the (science) newsletter"
    assert schema_org["author"] == [
        {
            "id": "https://orcid.org/0000-0003-1419-2405",
            "givenName": "Martin",
            "familyName": "Fenner",
            "@type": "Person",
            "name": "Martin Fenner",
        }
    ]


def test_get_formatted_metadata_datacite():
    "get doi metadata in datacite format"
    data = path.join(path.dirname(__file__), "fixtures", "commonmeta.json")
    result = get_formatted_metadata(data, format_="datacite")
    datacite = json.loads(result["data"])
    assert datacite["titles"][0].get("title") == "The rise of the (science) newsletter"
    assert datacite["creators"] == [
        {
            "familyName": "Fenner",
            "givenName": "Martin",
            "name": "Fenner, Martin",
            "nameIdentifiers": [
                {
                    "nameIdentifier": "https://orcid.org/0000-0003-1419-2405",
                    "nameIdentifierScheme": "ORCID",
                    "schemeUri": "https://orcid.org",
                }
            ],
            "nameType": "Personal",
        }
    ]


def test_get_formatted_metadata_citation():
    "get doi metadata as formatted citation"
    data = path.join(path.dirname(__file__), "fixtures", "commonmeta.json")
    result = get_formatted_metadata(data, format_="citation")
    assert (
        result["data"]
        == "Fenner, M. (2023). <i>The rise of the (science) newsletter</i>. https://doi.org/10.53731/ybhah-9jy85"
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


def test_start_case_single_character():
    """capitalize first letter without lowercasing the rest"""
    content = "r"
    assert start_case(content) == "R"


def test_start_case_with_space():
    """capitalize first letter without lowercasing the rest"""
    content = "wiki cite"
    assert start_case(content) == "Wiki Cite"


def test_normalize_tag():
    """normalize tag"""
    tag = "#open science"
    assert normalize_tag(tag) == "Open Science"


def test_normalize_tag_fixed():
    """normalize tag fixed"""
    tag = "#OSTP"
    assert normalize_tag(tag) == "OSTP"


def test_normalize_tag_escaped():
    """normalize tag escaped"""
    tag = "Forschungsinformationen &amp; Systeme"
    assert normalize_tag(tag) == "Forschungsinformationen & Systeme"


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
    text = """Le logiciel libre Pandoc par John MacFarlane est un outil très utile : 
    par exemple, Yanina Bellini Saibene, community manager de rOpenSci, a récemment 
    demandé à Maëlle si elle pouvait convertir un document Google en livre Quarto."""
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
        "affiliation": [
            {
                "id": "https://ror.org/052gg0110",
                "name": "University of Oxford",
                "start_date": "1981-01-01",
            }
        ],
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


def test_extract_atom_authors():
    """extract authors from atom feed"""
    authors = {"name": "Bosun Obileye and Josiline Chigwada"}
    result = extract_atom_authors(authors)
    assert result == [{"name": "Bosun Obileye"}, {"name": "Josiline Chigwada"}]


def test_extract_atom_authors_with_comma():
    """extract authors from atom feed with comma"""
    authors = {
        "name": "Kelly Stathis, Cody Ross, Ashwini Sukale, Kudakwashe Siziva and Suzanne Vogt"
    }
    result = extract_atom_authors(authors)
    assert result == [
        {"name": "Kelly Stathis"},
        {"name": "Cody Ross"},
        {"name": "Ashwini Sukale"},
        {"name": "Kudakwashe Siziva"},
        {"name": "Suzanne Vogt"},
    ]


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
    assert result == "https://www.ch.imperial.ac.uk/rzepa/blog/?p=25304"


def test_normalize_url_without_scheme():
    """normalize url without scheme"""
    url = "www.openmake.de/blog/2024/06/26/2024-06-26-mobilelab/"
    result = normalize_url(url)
    assert result == "https://www.openmake.de/blog/2024/06/26/2024-06-26-mobilelab"


def test_is_valid_url():
    """is valid url"""
    assert True == is_valid_url("https://www.example.com")
    assert True == is_valid_url("http://www.example.com")
    assert True == is_valid_url("//www.example.com")


def test_get_markdown():
    """get markdown from html"""
    html = "<p>This is a <em>test</em></p>"
    result = get_markdown(html)
    assert result == "This is a *test*\n"


def test_format_markdown():
    """format markdown"""
    content = "This is a *test*"
    metadata = {"title": "Test"}
    result = format_markdown(content, metadata)
    result = frontmatter.dumps(result)
    assert (
        result
        == """---
date: '1970-01-01T00:00:00+00:00'
date_updated: '1970-01-01T00:00:00+00:00'
issn: null
rights: null
summary: ''
title: Test
---

This is a *test*"""
    )


def test_format_epub():
    """format epub"""
    content = "This is a *test*"
    metadata = {"title": "Test"}
    markdown = format_markdown(content, metadata)
    result = write_epub(markdown)
    assert result is not None
    # post = epub.read_epub(result)
    # assert post.metadata == "Test"


def test_format_pdf():
    """format pdf"""
    content = "This is a *test*"
    metadata = {"title": "Test"}
    markdown = format_markdown(content, metadata)
    result = write_pdf(markdown)
    assert result is not None
    # reader = PdfReader(result)
    # number_of_pages = len(reader.pages)
    # assert number_of_pages == 1


def test_format_html():
    """format html"""
    content = "This is a *test*"
    result = write_html(content)
    assert result == "<p>This is a <em>test</em></p>\n"


def test_id_as_str():
    """id as string"""
    assert "10.5555/1234" == id_as_str("https://doi.org/10.5555/1234")
    assert "www.gooogle.com/blabla" == id_as_str("https://www.gooogle.com/blabla")


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


@pytest.mark.asyncio
async def test_get_single_work_blog_post():
    """get single work not found"""
    string = "10.53731/ybhah-9jy85"
    work = await get_single_work(string)
    assert work["id"] == "https://doi.org/10.53731/ybhah-9jy85"
    assert work["type"] == "BlogPost"
    assert (
        work["url"]
        == "https://blog.front-matter.io/posts/the-rise-of-the-science-newsletter"
    )
    assert work.get("language", None) == None


@pytest.mark.asyncio
async def test_get_single_work_journal_article():
    """get single work journal article"""
    string = "10.1038/d41586-023-02554-0"
    work = await get_single_work(string)
    assert work["id"] == "https://doi.org/10.1038/d41586-023-02554-0"
    assert work["type"] == "JournalArticle"
    assert work["url"] == "https://www.nature.com/articles/d41586-023-02554-0"


@pytest.mark.asyncio
async def test_get_single_work_software():
    """get single work software"""
    string = "10.5281/zenodo.8340374"
    work = await get_single_work(string)
    assert work["id"] == "https://doi.org/10.5281/zenodo.8340374"
    assert work["type"] == "Software"
    assert work["url"] == "https://zenodo.org/doi/10.5281/zenodo.8340374"


@pytest.mark.asyncio
async def test_get_single_work_dataset():
    """get single work dataset"""
    string = "10.5281/zenodo.7834392"
    work = await get_single_work(string)
    assert work["id"] == "https://doi.org/10.5281/zenodo.7834392"
    assert work["type"] == "Dataset"
    assert work["url"] == "https://zenodo.org/record/7834392"


@pytest.mark.asyncio
async def test_format_reference_blog_post():
    """format reference blog post"""
    url = "https://doi.org/10.53731/ybhah-9jy85"
    work = await format_reference(url, True)
    assert work["id"] == "https://doi.org/10.53731/ybhah-9jy85"
    assert (
        work["unstructured"]
        == "Fenner, M. (2023, October 4). The rise of the (science) newsletter. <i>Front Matter</i>. https://doi.org/10.53731/ybhah-9jy85"
    )


@pytest.mark.asyncio
async def test_format_reference_journal_article():
    """format reference journal article"""
    url = "https://doi.org/10.1038/d41586-023-02554-0"
    work = await format_reference(url, True)
    assert work["id"] == "https://doi.org/10.1038/d41586-023-02554-0"
    assert (
        work["unstructured"]
        == "Vidal Valero, M. (2023). Thousands of scientists are cutting back on Twitter, seeding angst and uncertainty. <i>Nature</i>, <i>620</i>(7974), 482–484. https://doi.org/10.1038/d41586-023-02554-0"
    )


@pytest.mark.asyncio
async def test_format_reference_software():
    """format reference software"""
    url = "https://doi.org/10.5281/zenodo.8340374"
    work = await format_reference(url, True)
    assert work["id"] == "https://doi.org/10.5281/zenodo.8340374"
    assert (
        work["unstructured"]
        == "Fenner, M. (2024). <i>commonmeta-py</i> (013.2) [Computer software]. Zenodo. https://doi.org/10.5281/zenodo.8340374"
    )


def test_extract_extract_reference_id_doi():
    """extract reference_id doi"""
    reference = """Boisvert, C., Bivens, G., Curtice, B., Wilhite, R., & Wedel, M. (2025). 
    Census of currently known specimens of the Late Jurassic sauropod Haplocanthosaurus 
    from the Morrison Formation, USA. Geology of the Intermountain West, 12, 1–23. 
    https://doi.org/10.31711/giw.v12.pp1-23"""
    result = extract_reference_id(reference)
    assert result == "https://doi.org/10.31711/giw.v12.pp1-23"


def test_extract_extract_reference_id_url():
    """extract reference_id url"""
    reference = """Boisvert, C., Bivens, G., Curtice, B., Wilhite, R., & Wedel, M. (2025). 
    Census of currently known specimens of the Late Jurassic sauropod Haplocanthosaurus 
    from the Morrison Formation, USA. Geology of the Intermountain West, 12, 1–23. 
    https://giw.utahgeology.org/giw/index.php/GIW/article/view/150"""
    result = extract_reference_id(reference)
    assert result == "https://giw.utahgeology.org/giw/index.php/GIW/article/view/150"


@pytest.mark.asyncio
async def test_format_list_reference():
    """format reference from list"""
    reference = """<a href="http://doi.org/10.1002/ar.25520">Boisvert, Colin, Curtice, Brian, Wedel, Mathew, &amp; Wilhite, Ray. 2024. Description of a new specimen of&nbsp;<em>Haplocanthosaurus</em>&nbsp;from the Dry Mesa Dinosaur Quarry. The Anatomical Record, 1–19. http://doi.org/10.1002/ar.25520</a>"""
    soup = get_soup(reference)
    result = await format_list_reference(soup)
    assert result == {
        "id": "http://doi.org/10.1002/ar.25520",
        "unstructured": "Boisvert, Colin, Curtice, Brian, Wedel, Mathew, & Wilhite, Ray. 2024. Description of a new specimen of\xa0Haplocanthosaurus\xa0from the Dry Mesa Dinosaur Quarry. The Anatomical Record, 1–19. http://doi.org/10.1002/ar.25520",
    }


@pytest.mark.asyncio
async def test_format_list_reference_curie():
    """format reference from list curie"""
    reference = """Melstrom, Keegan M., Michael D. D’Emic, Daniel Chure and Jeffrey A. Wilson. 2016. A juvenile sauropod dinosaur from the Late Jurassic of Utah, USA, presents further evidence of an avian style air-sac system. Journal of Vertebrate Paleontology 36(4):e1111898. doi:10.1080/02724634.2016.1111898"""
    soup = get_soup(reference)
    result = await format_list_reference(soup)
    assert result == {
        "id": "https://doi.org/10.1080/02724634.2016.1111898",
        "unstructured": "Melstrom, Keegan M., Michael D. D’Emic, Daniel Chure and Jeffrey A. Wilson. 2016. A juvenile sauropod dinosaur from the Late Jurassic of Utah, USA, presents further evidence of an avian style air-sac system. Journal of Vertebrate Paleontology 36(4):e1111898. https://doi.org/10.1080/02724634.2016.1111898",
    }


@pytest.mark.asyncio
async def test_parse_blogger_guid():
    """Parse Blogger GUID to extract blog ID and post ID."""
    guid = "tag:blogger.com,1999:blog-3536726.post-106726196118183051"
    result = await parse_blogger_guid(guid)
    assert result == ("3536726", "106726196118183051")


def test_extract_wordpress_post_id():
    """Extract WordPress post ID from a GUID."""
    guid = "https://cstonline.ca.reclaim.press/?p=598"
    result = extract_wordpress_post_id(guid)
    assert result == "598"
