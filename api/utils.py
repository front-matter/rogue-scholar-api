"""Utility functions"""
from uuid import UUID
from typing import Optional, Union
import re
import requests
import json
import iso8601
import html
from lxml import etree
import bibtexparser
from bibtexparser.model import Field
import pydash as py_
from dateutil import parser, relativedelta
from datetime import datetime
from furl import furl
from langdetect import detect
from bs4 import BeautifulSoup
from idutils import is_orcid
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
    url_ = url if url and is_orcid(url) else AUTHOR_IDS.get(name_, None)

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


def get_doi_metadata_from_ra(
    doi: str, format_: str = "csl", style: str = "apa", locale: str = "en-US"
) -> Optional[dict]:
    """use DOI content negotiation to get metadata in various formats.
    format_ can be bibtex, ris, csl, citation, with bibtex as default."""

    content_types = {
        "bibtex": "application/x-bibtex",
        "ris": "application/x-research-info-systems",
        "csl": "application/vnd.citationstyles.csl+json",
        "citation": f"text/x-bibliography; style={style}; locale={locale}",
    }
    content_type = content_types.get(format_)
    
    response = requests.get(doi, headers={"Accept": content_type}, timeout=10)
    response.encoding = "UTF-8"
    if response.status_code >= 400:
        return None

    basename = doi_from_url(doi).replace("/", "-")
    if format_ == "csl":
        ext = "json"
        csl = response.json()

        # cleanup to align with CSL spec
        csl = py_.omit(csl, ["license", "original-title"])
        csl["id"] = doi
        csl["title"] = html.unescape(csl["title"])

        # correctly parse metadata for posted_content type
        if csl["type"] == "posted-content":
            csl["type"] = "article-journal"
            csl["container-title"] = py_.get(csl, "institution[0].name", None)

        result = json.dumps(csl, indent=2)
    elif format_ == "ris":
        ext = "ris"
        result = response.text
    elif format_ == "bibtex":
        ext = "bib"
        bib = bibtexparser.parse_string(response.text)
        entry = bib.entries[0]
        
        # cleanup to bibtex
        # TODO: fix more fields
        entry.set_field(Field(key="DOI", value=doi_from_url(doi)))
        result = bibtexparser.write_string(bib)
    else:
        ext = "txt"
        result = response.text
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
    p = etree.fromstring(x, parser = etree.XMLParser(recover=True))
    return etree.tostring(p)


def get_markdown(content_html: str) -> str:
    """Get markdown from html"""
    try:
        doc = pandoc.read(content_html, format="html")
        return pandoc.write(doc, format="commonmark_x")
    except Exception as e:
        print(e)
        return ""
    
    
def format_markdown(content: str, metadata) -> str:
    """format markdown"""
    post = frontmatter.Post(content, **metadata)
    post['date'] = datetime.utcfromtimestamp(metadata.get("date", 0)).isoformat() + "Z"
    post['updated_date'] = datetime.utcfromtimestamp(metadata.get("updated_date", 0)).isoformat() + "Z"
    post['abstract'] = metadata.get("abstract", "").strip()
    return frontmatter.dumps(post)
