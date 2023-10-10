import requests
import datetime
import iso8601
from uuid import UUID
# import re
from typing import Optional



# def sanitize_suffix(str):
#     # Regular expression to only allow certain characters in DOI suffix
#     # taken from https://www.crossref.org/blog/dois-and-matching-regular-expressions/
#     m = re.match(r"^\[-._;\(\)/:A-Z0-9\]+$", str)
#     print(m)
#     return m

def unix_timestamp(date_str: str) -> int:
    """convert edtf level 0 iso8601 date to unix timestamp"""
    dt = iso8601.parse_date(date_str)

     # date = datetime.date.fromisoformat(date_str)
    # midnight = datetime.datetime.combine(datetime, datetime.datetime.min.time())
    print(int(dt.timestamp()))
    return int(dt.timestamp())


def validate_uuid(slug: str) -> bool:
    """validate uuid"""
    try:
        UUID(slug, version=4)
        return True
    except ValueError:
        return False


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
    response = requests.get(doi, headers={"Accept": content_type})
    response.encoding = "UTF-8"
    if response.status_code >= 400:
        return None
    basename = doi.replace("/", "-")
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
