from typing import Optional
import orjson as json
from postgrest.exceptions import APIError
from commonmeta import Metadata
from commonmeta.doi_utils import is_rogue_scholar_doi, doi_from_url

from api.supabase import (
    supabase_admin_client as supabase_admin,
    supabase_client as supabase,
    worksSelect,
)

# supported accept headers for content negotiation
SUPPORTED_ACCEPT_HEADERS = [
    "application/vnd.commonmeta+json",
    "application/x-bibtex",
    "application/x-research-info-systems",
    "application/vnd.citationstyles.csl+json",
    "application/vnd.schemaorg.ld+json",
    "application/vnd.datacite.datacite+json",
    "application/vnd.crossref.unixref+xml",
    "text/x-bibliography",
]


async def fetch_single_work(string: str) -> Optional[dict]:
    """Fetch single work."""
    # use Rogue Scholar API if the work is a Rogue Scholar DOI,
    # as Crossref doesn't store all metadata
    if is_rogue_scholar_doi(string):
        string = f"https://api.rogue-scholar.org/posts/{doi_from_url(string)}"
    work = Metadata(string)
    return json.loads(work.write())


def upsert_single_work(work):
    """Upsert single work."""

    if not work.get("id", None) or not work.get("type", None):
        return None

    try:
        response = (
            supabase_admin.table("works")
            .upsert(
                {
                    "id": work.get("id"),
                    "type": work.get("type"),
                    "url": work.get("url", None),
                    "contributors": work.get("contributors", []),
                    "titles": work.get("titles", []),
                    "container": work.get("container", None),
                    "publisher": work.get("publisher", None),
                    "references": work.get("references", []),
                    "relations": work.get("relations", []),
                    "date": work.get("date", None),
                    "descriptions": work.get("descriptions", []),
                    "license": work.get("license", None),
                    "alternate_identifiers": work.get("alternate_identifiers", []),
                    "funding_references": work.get("funding_references", []),
                    "files": work.get("files", []),
                    "subjects": work.get("subjects", []),
                    "provider": work.get("provider", None),
                    "schema_version": work.get("schema_version", None),
                    "state": work.get("state", None),
                    "archive_locations": work.get("archive_locations", []),
                    "geo_locations": work.get("geo_locations", []),
                    "version": work.get("version", None),
                    "language": work.get("language", None),
                    "additional_type": work.get("additional_type", None),
                    "sizes": work.get("sizes", []),
                    "formats": work.get("formats", []),
                },
                returning="representation",
                ignore_duplicates=False,
                on_conflict="id",
            )
            .execute()
        )
        return response.data[0]
    except Exception as e:
        print(e)
        return None


async def get_single_work(string: str) -> Optional[dict]:
    """Get single work from the works table, or fetch from the internt."""
    try:
        response = (
            supabase.table("works")
            .select(worksSelect, count="exact")
            .eq("id", string)
            .maybe_single()
            .execute()
        )
    except Exception as e:
        # if work not found, fetch from the internet
        if e.code == "204":
            work = await fetch_single_work(string)
            return upsert_single_work(work)
        print(e)
        return None

    return response.data


def update_single_work(string: str) -> Optional[dict]:
    """Update single work from the internt."""

    work = fetch_single_work(string)
    return upsert_single_work(work)


def get_formatted_work(
    subject, accept_header: str, style: str = "apa", locale: str = "en-US"
):
    """Get formatted work."""
    accept_headers = {
        "application/vnd.commonmeta+json": "commonmeta",
        "application/x-bibtex": "bibtex",
        "application/x-research-info-systems": "ris",
        "application/vnd.citationstyles.csl+json": "csl",
        "application/vnd.schemaorg.ld+json": "schema_org",
        "application/vnd.datacite.datacite+json": "datacite",
        "application/vnd.crossref.unixref+xml": "crossref_xml",
        "text/x-bibliography": "citation",
    }
    content_type = accept_headers.get(accept_header, "commonmeta")
    if content_type == "citation":
        # workaround for properly formatting blog posts
        subject.type = "JournalArticle"
        return subject.write(to="citation", style=style, locale=locale)
    else:
        return subject.write(to=content_type)
