from typing import Optional
from os import environ
import httpx

# from api.supabase import (
#     supabase_client as supabase,
#     supabase_admin_client as supabase_admin,
# )

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


async def get_single_work(string: str) -> Optional[dict]:
    """Get single work from the commonmeta API."""

    url = f"{environ["QUART_POCKETBASE_URL"]}/{string}/transform/application/json"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            return response.json()
    except Exception as exc:
        print(exc)
        return None


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
