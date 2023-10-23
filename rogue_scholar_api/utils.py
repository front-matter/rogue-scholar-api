"""Utility functions"""
from uuid import UUID
from typing import Optional
import requests
import iso8601
from dateutil import parser
from furl import furl

from commonmeta.doi_utils import doi_from_url


# def sanitize_suffix(str):
#     # Regular expression to only allow certain characters in DOI suffix
#     # taken from https://www.crossref.org/blog/dois-and-matching-regular-expressions/
#     m = re.match(r"^\[-._;\(\)/:A-Z0-9\]+$", str)
#     print(m)
#     return m


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
}


def get_date(date: str):
    """Get iso8601 date from string."""
    if not date:
        return None
    try:
        return parser.parse(date).isoformat("T","seconds")
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
    doi: str, format_: str = "bibtex", style: str = "apa", locale: str = "en-US"
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
    elif format_ == "ris":
        ext = "ris"
    elif format_ == "bibtex":
        ext = "bib"
    else:
        ext = "txt"
    options = {
        "Content-Type": content_type,
        "Content-Disposition": f"attachment; filename={basename}.{ext}",
    }
    return {"doi": doi, "data": response.text.strip(), "options": options}


# def format_metadata(meta: dict, to: str = "bibtex"):
#     """use commonmeta-py library to format metadata into various formats"""
#     print(meta)
#     subject = Metadata(meta)

#     if to == "bibtex":
#         return write_bibtex(subject)
#     elif to == "ris":
#         return write_ris(subject)
#     elif to == "csl":
#         return write_csl(subject)
#     elif to == "citation":
#         return write_citation(subject)


def normalize_url(url: Optional[str], secure=False, lower=False) -> Optional[str]:
    """Normalize URL"""
    if url is None or not isinstance(url, str):
        return None
    f = furl(url)
    f.path.normalize()
    f.remove(fragment=True)
    if secure and f.scheme == "http":
        f.set(scheme='https')
    if lower:
        return f.url.lower().strip("/")
    return f.url.strip("/")
