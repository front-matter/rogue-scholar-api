"""Citations module."""

from os import environ
from typing import Optional
import httpx
import xmltodict
import re
from furl import furl
import datetime
import pydash as py_
from commonmeta import validate_doi, normalize_doi, Metadata

from api.supabase_client import (
    supabase_client as supabase,
    supabase_admin_client as supabase_admin,
)
from api.utils import (
    compact,
    start_case,
    get_date,
    unix_timestamp,
    wrap,
    normalize_url,
    is_valid_url,
    format_datetime,
    FOS_MAPPINGS,
)


async def extract_all_citations_by_prefix(prefix: Optional[str]) -> list:
    """Extract all citations from Crossref cited-by service by prefix. Needs username and password for account
    managing the prefix."""
    username = environ.get("QUART_CROSSREF_USERNAME_WITH_ROLE", None)
    password = environ.get("QUART_CROSSREF_PASSWORD", None)
    if not username or not password or not prefix:
        return []

    url = f"https://doi.crossref.org/servlet/getForwardLinks?usr={username}&pwd={password}&doi={prefix}&startDate=2021-01-01&include_postedcontent=true"
    response = httpx.get(url, headers={"Accept": "text/xml;charset=utf-8"}, timeout=10)
    response.raise_for_status()
    crossref_result = xmltodict.parse(response.text)
    citations = py_.get(
        crossref_result, "crossref_result.query_result.body.forward_link", []
    )
    return await upsert_citations(citations)


def parse_crossref_xml(xml: Optional[str], **kwargs) -> list:
    """Parse Crossref XML."""
    if not xml:
        return []

    # remove namespaces from xml
    namespaces = {
        "http://www.crossref.org/qrschema/3.0": None,
    }
    kwargs["process_namespaces"] = True
    kwargs["namespaces"] = namespaces
    kwargs["force_list"] = {"forward_link"}

    kwargs["attr_prefix"] = ""
    kwargs["dict_constructor"] = dict
    kwargs.pop("dialect", None)
    return xmltodict.parse(xml, **kwargs)


async def format_crossref_citation(citation: dict) -> dict:
    """Format Crossref citation from Crossref cited-by service.
    Citing doi is embedded in different metadata, depending on the content type, e.g. journal_cite, book_cite, etc."""

    cited_doi = validate_doi(citation.get("@doi", None))
    citing_doi = validate_doi(
        py_.get(citation, "journal_cite.doi.#text")
        or py_.get(citation, "book_cite.doi.#text")
        or py_.get(citation, "postedcontent_cite.doi.#text")
        or py_.get(citation, "conf_cite.doi.#text")
    )

    if cited_doi is None or citing_doi is None:
        return {}

    # generate unique identifier using cited_doi and citing_doi
    # TODO: align with OpenCitations OCI identifier

    cid = f"{cited_doi.lower()}::{citing_doi.lower()}"

    # lookup metadata via API call, as we need the publication date to order the citations
    subject = Metadata(citing_doi)

    unstructured = subject.write(to="citation", style="apa", locale="en-US")
    published_at = py_.get(subject, "date.published")

    return compact(
        {
            "cid": cid,
            "doi": normalize_doi(cited_doi),
            "citation": normalize_doi(citing_doi),
            "unstructured": unstructured,
            "published_at": published_at,
        }
    )


async def upsert_citations(citations: list) -> list:
    """Upsert multiple citations."""
    data = [await format_crossref_citation(citation) for citation in citations]
    return [await upsert_single_citation(citation) for citation in data]


async def upsert_single_citation(citation):
    """Upsert single citation."""

    # missing doi, citation or oci
    # oci is used as unique identifier for the citation record
    if not citation.get("doi", None) or not citation.get("citation", None):
        return {}

    try:
        response = (
            supabase_admin.table("citations")
            .upsert(
                {
                    "cid": citation.get("cid"),
                    "doi": citation.get("doi"),
                    "citation": citation.get("citation"),
                    "unstructured": citation.get("unstructured", None),
                    "published_at": citation.get("published_at", None),
                },
                returning="representation",
                ignore_duplicates=False,
                on_conflict="cid",
            )
            .execute()
        )
        data = response.data[0]
        return data
    except Exception as e:
        print(e)
        return None
