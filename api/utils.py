"""Utility functions"""
from uuid import UUID
from typing import Optional, Union
import re
from babel.dates import format_date
import requests
import json
import iso8601
import html
from lxml import etree
import bibtexparser
import pydash as py_
from dateutil import parser, relativedelta
from datetime import datetime
from furl import furl
from langdetect import detect
from bs4 import BeautifulSoup
from commonmeta import (
    Metadata,
    get_one_author,
    validate_orcid,
    normalize_orcid,
    json_feed_reader,
)
from commonmeta.constants import Commonmeta
from commonmeta.date_utils import get_date_from_unix_timestamp
from commonmeta.doi_utils import validate_prefix, get_doi_ra
import frontmatter
import pandoc
# from pandoc.types import Str


AUTHOR_IDS = {
    "Kristian Garza": "https://orcid.org/0000-0003-3484-6875",
    "Roderic Page": "https://orcid.org/0000-0002-7101-9767",
    "Tejas S. Sathe": "https://orcid.org/0000-0003-0449-4469",
    "Meghal Shah": "https://orcid.org/0000-0002-2085-659X",
    "Liberate Science": "https://ror.org/0342dzm54",
    "Lars Willighagen": "https://orcid.org/0000-0002-4751-4637",
    "Marco Tullney": "https://orcid.org/0000-0002-5111-2788",
    "Andrew Heiss": "https://orcid.org/0000-0002-3948-3914",
    "Sebastian Karcher": "https://orcid.org/0000-0001-8249-7388",
    "Colin Elman": "https://orcid.org/0000-0003-1004-4640",
    "Veronica Herrera": "https://orcid.org/0000-0003-4935-1226",
    "Dessislava Kirilova": "https://orcid.org/0000-0002-3824-9982",
    "Corin Wagen": "https://orcid.org/0000-0003-3315-3524",
    "Adèniké Deane-Pratt": "https://orcid.org/0000-0001-9940-9233",
    "Angela Dappert": "https://orcid.org/0000-0003-2614-6676",
    "Laura Rueda": "https://orcid.org/0000-0001-5952-7630",
    "Rachael Kotarski": "https://orcid.org/0000-0001-6843-7960",
    "Florian Graef": "https://orcid.org/0000-0002-0716-5639",
    "Adam Farquhar": "https://orcid.org/0000-0001-5331-6592",
    "Tom Demeranville": "https://orcid.org/0000-0003-0902-4386",
    "Martin Fenner": "https://orcid.org/0000-0003-1419-2405",
    "Sünje Dallmeier-Tiessen": "https://orcid.org/0000-0002-6137-2348",
    "Maaike Duine": "https://orcid.org/0000-0003-3412-7192",
    "Kirstie Hewlett": "https://orcid.org/0000-0001-5853-0432",
    "Amir Aryani": "https://orcid.org/0000-0002-4259-9774",
    "Xiaoli Chen": "https://orcid.org/0000-0003-0207-2705",
    "Patricia Herterich": "https://orcid.org/0000-0002-4542-9906",
    "Josh Brown": "https://orcid.org/0000-0002-8689-4935",
    "Robin Dasler": "https://orcid.org/0000-0002-4695-7874",
    "Markus Stocker": "https://orcid.org/0000-0001-5492-3212",
    "Robert Petryszak": "https://orcid.org/0000-0001-6333-2182",
    "Robert Huber": "https://orcid.org/0000-0003-3000-0020",
    "Sven Lieber": "https://orcid.org/0000-0002-7304-3787",
    "David M. Shotton": "https://orcid.org/0000-0001-5506-523X",
    "Heinz Pampel": "https://orcid.org/0000-0003-3334-2771",
    "Martin Paul Eve": "https://orcid.org/0000-0002-5589-8511",
}

AUTHOR_NAMES = {
    "GPT-4": "Tejas S. Sathe",
    "Morgan & Ethan": "Morgan Ernest",
    "Marco": "Marco Tullney",
    "NFernan": "Norbisley Fernández",
    "skarcher@syr.edu": "Sebastian Karcher",
    "celman@maxwell.syr.edu": "Colin Elman",
    "colinelman@twcny.rr.com": "Colin Elman",
    "veronica.herrera@uconn.edu": "Veronica Herrera",
    "dessi.kirilova@syr.edu": "Dessislava Kirilova",
    "benosteen": "Ben O'Steen",
    "marilena_daquino": "Marilena Daquino",
    "markmacgillivray": "Mark MacGillivray",
    "richarddjones": "Richard Jones",
    "maaikeduine": "Maaike Duine",
    "suenjedt": "Sünje Dallmeier-Tiessen",
    "kirstiehewlett": "Kirstie Hewlett",
    "pherterich": "Patricia Herterich",
    "adeanepratt": "Adèniké Deane-Pratt",
    "angeladappert": "Angela Dappert",
    "RachaelKotarski": "Rachael Kotarski",
    "fgraef": "Florian Graef",
    "adamfarquhar": "Adam Farquhar",
    "tomdemeranville": "Tom Demeranville",
    "mfenner": "Martin Fenner",
    "davidshotton": "David M. Shotton",
    "meineckei": "Isabella Meinecke",
    "schradera": "Antonia Schrader",
    "arningu": "Ursula Arning",
    "rmounce": "Ross Mounce",
}


def wrap(item) -> list:
    """Turn None, dict, or list into list"""
    if item is None:
        return []
    if isinstance(item, list):
        return item
    return [item]


def compact(dict_or_list: Union[dict, list]) -> Optional[Union[dict, list]]:
    """Remove None from dict or list"""
    if isinstance(dict_or_list, dict):
        return {k: v for k, v in dict_or_list.items() if v is not None}
    if isinstance(dict_or_list, list):
        lst = [compact(i) for i in dict_or_list]
        return lst if len(lst) > 0 else None

    return None


def doi_from_url(url: str) -> Optional[str]:
    """Return a DOI from a URL"""
    match = re.search(
        r"\A(?:(http|https)://(dx\.)?(doi\.org|handle\.stage\.datacite\.org|handle\.test\.datacite\.org)/)?(doi:)?(10\.\d{4,5}/.+)\Z",
        url,
    )
    if match is None:
        return None
    return match.group(5).lower()


def normalize_author(name: str, url: str = None) -> dict:
    """Normalize author name and url. Strip text after comma
    if suffix is an academic title"""

    if name.split(", ", maxsplit=1)[-1] in ["MD", "PhD"]:
        name = name.split(", ", maxsplit=1)[0]

    name_ = AUTHOR_NAMES.get(name, None) or name
    url_ = url if url and validate_orcid(url) else AUTHOR_IDS.get(name_, None)

    return compact({"name": name_, "url": url_})


def get_date(date: str):
    """Get iso8601 date from string."""
    if not date:
        return None
    try:
        return parser.parse(date).isoformat("T", "seconds")
    except Exception as e:
        print(e)
        return None


def unix_timestamp(date_str: str) -> int:
    """convert iso8601 date to unix timestamp"""
    try:
        dt = iso8601.parse_date(date_str)
        return int(dt.timestamp())
    except ValueError as e:
        print(e)
        return 0


def format_datetime(date_str: str, lc: str = "en") -> str:
    """convert iso8601 date to formatted date"""
    try:
        dt = iso8601.parse_date(date_str)
        return format_date(dt, format="long", locale=lc)
    except ValueError as e:
        print(e)
        return "January 1, 1970"


def end_of_date(date_str: str) -> str:
    """convert iso8601 date to end of day/month/year"""
    try:
        date = date_str.split("-")
        dt = iso8601.parse_date(date_str)
        month, day, hour, minute, second = (
            dt.month,
            dt.day,
            dt.hour,
            dt.minute,
            dt.second,
        )
        month = 12 if len(date) < 2 else month
        day = 31 if len(date) < 3 else day
        hour = 23 if hour == 0 else hour
        minute = 59 if minute == 0 else minute
        second = 59 if second == 0 else second
        dt = dt + relativedelta.relativedelta(
            month=month, day=day, hour=hour, minute=minute, second=second
        )
        return dt.isoformat("T", "seconds")
    except ValueError as e:
        print(e)
        return "1970-01-01T00:00:00"


def format_authors(authors):
    """Extract author names"""

    def format_author(author):
        return author.get("name", None)

    return [format_author(x) for x in authors]


def format_authors_full(authors):
    """Parse author names into given and family names"""

    def format_author(author):
        meta = get_one_author(author)
        given_names = meta.get("givenName", None)
        surname = meta.get("familyName", None)
        name = meta.get("name", None)
        orcid = validate_orcid(author.get("url", None))
        return compact(
            {
                "orcid": orcid,
                "given-names": given_names,
                "surname": surname,
                "name": name,
            }
        )

    return [format_author(x) for x in authors]


def format_authors_commonmeta(authors):
    """Extract author names"""

    def format_author(author):
        return get_one_author(author)

    return [format_author(x) for x in authors]


def format_license(authors, date):
    """Generate license string"""

    auth = format_authors(authors)
    length = len(auth)
    year = date[:4]
    if length == 0:
        auth = ""
    if length > 0:
        auth = auth[0]
    if length > 1:
        auth = auth + " et al."
    return f'Copyright <span class="copyright">©</span> {auth} {year}.'


def format_relationships(relationships):
    "Format relationships metadata"

    def format_relationship(relationship):
        if relationship.get("type", None) == "IsIdenticalTo":
            return {"identical": relationship.get("url", None)}
        elif relationship.get("type", None) == "IsPreprintOf":
            return {"preprint": relationship.get("url", None)}
        elif relationship.get("type", None) == "HasAward":
            return {"funding": relationship.get("url", None)}

    return [format_relationship(x) for x in relationships]


def format_authors_with_orcid(authors):
    """Parse author names into names and orcid"""

    def format_author(author):
        name = author.get("name", None)
        orcid = normalize_orcid(author.get("url", None))
        return compact(
            {
                "orcid": orcid,
                "name": name,
            }
        )

    return [format_author(x) for x in authors]


def validate_uuid(slug: str) -> bool:
    """validate uuid"""
    try:
        UUID(slug, version=4)
        return True
    except ValueError:
        return False


def start_case(content: str) -> str:
    """Capitalize first letter of each word without lowercasing the rest"""
    words = content.split(" ")
    content = " ".join([word[0].upper() + word[1:] for word in words])
    return content


def normalize_tag(tag: str) -> str:
    """Normalize tag"""
    fixed_tags = {
        "aPKC": "aPKC",
        "CrossRef": "Crossref",
        "DataCite": "DataCite",
        "EU": "EU",
        "USA": "USA",
        "OSTP": "OSTP",
        "ElasticSearch": "ElasticSearch",
        "FoxP": "FoxP",
        "GigaByte": "GigaByte",
        "GigaDB": "GigaDB",
        "GraphQL": "GraphQL",
        "JATS": "JATS",
        "JISC": "JISC",
        "JSON-LD": "JSON-LD",
        "microCT": "MicroCT",
        "MTE14": "MTE14",
        "Pre-Print": "Preprint",
        "Q&A": "Q&A",
        "ResearchGate": "ResearchGate",
        "RStats": "RStats",
        "ScienceEurope": "Science Europe",
        "TreeBASE": "TreeBASE",
        "Web 2.0": "Web 2.0",
        "WikiCite": "WikiCite",
        "WikiData": "WikiData",
    }

    tag = tag.replace("#", "")
    return fixed_tags.get(tag, start_case(tag))


def convert_to_commonmeta(meta: dict) -> Commonmeta:
    """Convert post metadata to commonmeta format"""

    doi = doi_from_url(meta.get("doi", None))
    published = get_date_from_unix_timestamp(meta.get("published_at", 0))
    updated = get_date_from_unix_timestamp(meta.get("updated_at", None))
    container_title = py_.get(meta, "blog.title")
    identifier = py_.get(meta, "blog.issn")
    identifier_type = "ISSN" if identifier else None
    subjects = py_.human_case(py_.get(meta, "blog.category"))
    publisher = py_.get(meta, "blog.title")
    provider = get_known_doi_ra(doi) or get_doi_ra(doi)
    alternate_identifiers = [
        {"alternateIdentifier": meta.get("id"), "alternateIdentifierType": "UUID"}
    ]
    return {
        "id": meta.get("doi", None),
        "url": meta.get("url", None),
        "type": "Article",
        "contributors": format_authors_commonmeta(meta.get("authors", None)),
        "titles": [{"title": meta.get("title", None)}],
        "descriptions": [
            {"description": meta.get("summary", None), "descriptionType": "Abstract"}
        ],
        "date": {"published": published, "updated": updated},
        "publisher": {
            "name": publisher,
        },
        "container": compact(
            {
                "type": "Periodical",
                "title": container_title,
                "identifier": identifier,
                "identifierType": identifier_type,
            }
        ),
        "subjects": [{"subject": subjects}],
        "language": meta.get("language", None),
        "references": meta.get("reference", None),
        "funding_references": [],
        "license": {
            "id": "CC-BY-4.0",
            "url": "https://creativecommons.org/licenses/by/4.0/legalcode",
        },
        "provider": provider,
        "alternateIdentifiers": alternate_identifiers,
        "files": [
            {
                "url": meta.get("url", None),
                "mimeType": "text/html",
            },
            {
                "url": f"https://api.rogue-scholar.org/posts/{doi}.md",
                "mimeType": "text/plain",
            },
            {
                "url": f"https://api.rogue-scholar.org/posts/{doi}.pdf",
                "mimeType": "application/pdf",
            },
            {
                "url": f"https://api.rogue-scholar.org/posts/{doi}.epub",
                "mimeType": "application/epub+zip",
            },
            {
                "url": f"https://api.rogue-scholar.org/posts/{doi}.xml",
                "mimeType": "application/xml",
            },
        ],
        "schema_version": "https://commonmeta.org/commonmeta_v0.10.5.json",
    }


def get_doi_metadata(
    data: str = "{}",
    format_: str = "commonmeta",
    style: str = "apa",
    locale: str = "en-US",
):
    """use commonmeta library to get metadata in various formats.
    format_ can be bibtex, ris, csl, citation, with bibtex as default."""

    content_types = {
        "commonmeta": "application/vnd.commonmeta+json",
        "bibtex": "application/x-bibtex",
        "ris": "application/x-research-infJoo-systems",
        "csl": "application/vnd.citationstyles.csl+json",
        "schema_org": "application/vnd.schemaorg.ld+json",
        "datacite": "application/vnd.datacite.datacite+json",
        "crossref_xml": "application/vnd.crossref.unixref+xml",
        "citation": f"text/x-bibliography; style={style}; locale={locale}",
    }
    content_type = content_types.get(format_)
    subject = Metadata(data, via="commonmeta")
    doi = doi_from_url(subject.id)
    basename = doi_from_url(doi).replace("/", "-")
    if format_ == "commonmeta":
        ext = "json"
        result = subject.commonmeta()
    elif format_ == "csl":
        ext = "json"
        result = subject.csl()
    elif format_ == "ris":
        ext = "ris"
        result = subject.ris()
    elif format_ == "bibtex":
        ext = "bib"
        result = subject.bibtex()
    elif format_ == "schema_org":
        ext = "jsonld"
        result = subject.schema_org()
    elif format_ == "crossref_xml":
        ext = "xml"
        result = subject.crossref_xml()
    elif format_ == "datacite":
        ext = "json"
        result = subject.datacite()
    else:
        ext = "txt"
        # workaround for properly formatting blog posts
        subject.type = "JournalArticle"
        result = subject.citation()
    options = {
        "Content-Type": content_type,
        "Content-Disposition": f"attachment; filename={basename}.{ext}",
    }
    return {"doi": doi, "data": result.strip(), "options": options}


def normalize_url(url: Optional[str], secure=False, lower=False) -> Optional[str]:
    """Normalize URL"""
    if url is None or not isinstance(url, str):
        return None
    f = furl(url)
    f.path.normalize()

    # remove trailing slash, index.html
    if f.path.segments and f.path.segments[-1] in ["", "index.html"]:
        f.path.segments.pop(-1)

    # remove fragments
    f.remove(fragment=True)

    # remove specific query parameters
    f.remove(
        [
            "origin",
            "ref",
            "referrer",
            "source",
            "utm_content",
            "utm_medium",
            "utm_campaign",
            "utm_source",
        ]
    )
    if secure and f.scheme == "http":
        f.set(scheme="https")
    if lower:
        return f.url.lower().strip("/")
    return f.url.strip("/")


def get_src_url(src: str, url: str, home_page_url: str):
    """Get src url"""

    if is_valid_url(src):
        return src

    if src and src.startswith("/"):
        f = furl(home_page_url)
        f.path = ""
        url = f.url
    else:
        url = url + "/"
    return url + src


def is_valid_url(url: str) -> bool:
    """Check if url is valid"""
    try:
        f = furl(url)
        return f.scheme in ["http", "https", "data", "mailto"]
    except Exception:
        return False


def detect_language(text: str) -> str:
    """Detect language"""

    try:
        return detect(text)
    except Exception as e:
        print(e)
        return "en"


def get_soup(content_html: str) -> Optional[BeautifulSoup]:
    """Get soup from html"""
    try:
        soup = BeautifulSoup(content_html, "html.parser")
        return soup
    except Exception as e:
        print(e)
        return content_html


def fix_xml(x):
    p = etree.fromstring(x, parser=etree.XMLParser(recover=True))
    return etree.tostring(p)


def get_markdown(content_html: str) -> str:
    """Get markdown from html"""
    try:
        doc = pandoc.read(content_html, format="html")
        return pandoc.write(doc, format="commonmark_x")
    except Exception as e:
        print(e)
        return ""


def write_epub(markdown: str):
    """Get epub from markdown"""
    try:
        doc = pandoc.read(markdown, format="commonmark_x")
        return pandoc.write(doc, format="epub")
    except Exception as e:
        print(e)
        return ""


def write_pdf(markdown: str):
    """Get pdf from markdown"""
    try:
        doc = pandoc.read(markdown, format="commonmark_x")
        return pandoc.write(
            doc,
            format="pdf",
            options=[
                "--pdf-engine=weasyprint",
                "--pdf-engine-opt=--pdf-variant=pdf/ua-1",
                "--data-dir=environ['QUART_PANDOC_DATA_DIR']",
                "--template=default.html5",
                "--css=style.css",
            ],
        )
    except Exception as e:
        print(e)
        return ""


def write_jats(markdown: str):
    """Get jats from markdown"""
    try:
        doc = pandoc.read(markdown, format="commonmark_x")
        return pandoc.write(doc, format="jats", options=["--standalone"])
    except Exception as e:
        print(e)
        return ""


def format_markdown(content: str, metadata) -> str:
    """format markdown"""
    post = frontmatter.Post(content, **metadata)
    post["date"] = datetime.utcfromtimestamp(metadata.get("date", 0)).isoformat() + "Z"
    post["date_updated"] = (
        datetime.utcfromtimestamp(metadata.get("date_updated", 0)).isoformat() + "Z"
    )
    post["abstract"] = metadata.get("abstract", "").strip()
    post["rights"] = "https://creativecommons.org/licenses/by/4.0/legalcode"
    return post


def get_known_doi_ra(doi: str) -> str:
    """Get DOI registration agency from prefixes used in Rogue Scholar"""
    crossref_prefixes = [
        "10.53731",
        "10.54900",
        "10.59348",
        "10.59349",
        "10.59350",
    ]
    datacite_prefixes = [
        "10.34732",
        "10.57689",
    ]
    if doi is None:
        return None
    prefix = validate_prefix(doi)
    if prefix is None:
        return None
    if prefix in crossref_prefixes:
        return "Crossref"
    if prefix in datacite_prefixes:
        return "DataCite"
    return None


def translate_titles(markdown):
    """Translate titles into respective language"""
    lastsep = {"en": "and", "de": "und", "es": "y", "fr": "et", "it": "e", "pt": "e"}
    date_title = {
        "en": "Published",
        "de": "Veröffentlicht",
        "es": "Publicado",
        "fr": "Publié",
        "it": "Pubblicato",
        "pt": "Publicados",
    }
    keywords_title = {
        "en": "Keywords",
        "de": "Schlüsselwörter",
        "es": "Palabras clave",
        "fr": "Mots clés",
        "it": "Parole chiave",
        "pt": "Palavras-chave",
    }
    citation_title = {
        "en": "Citation",
        "de": "Zitiervorschlag",
        "es": "Cita",
        "fr": "Citation",
        "it": "Citazione",
        "pt": "Citação",
    }
    copyright_title = {
        "en": "Copyright",
        "de": "Urheberrecht",
        "es": "Copyright",
        "fr": "Droit d'auteur",
        "it": "Copyright",
        "pt": "Direitos de autor",
    }
    lang = markdown.get("lang", "en")
    markdown["lastsep"] = lastsep.get(lang, "and")
    markdown["date-title"] = date_title.get(lang, "Published")
    markdown["keywords-title"] = keywords_title.get(lang, "Keywords")
    markdown["citation-title"] = citation_title.get(lang, "Citation")
    markdown["copyright-title"] = copyright_title.get(lang, "Copyright")
    return markdown
