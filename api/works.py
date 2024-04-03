from typing import Optional
import orjson as json
import pydash as py_
from commonmeta import Metadata
from commonmeta.base_utils import compact
from commonmeta.doi_utils import is_rogue_scholar_doi, doi_from_url
from commonmeta.utils import normalize_id
from pocketbase.utils import ClientResponseError

from api.pocketbase import pocketbase_client, admin_data

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
    # Fetch metadata from the internet, using commonmeta-py
    # use Rogue Scholar API if the work is a Rogue Scholar DOI,
    # as Crossref doesn't store all metadata
    if is_rogue_scholar_doi(string):
        string = f"https://api.rogue-scholar.org/posts/{doi_from_url(string)}"
    work = Metadata(string)
    return json.loads(work.write())


async def get_single_work(string: str) -> Optional[dict]:
    """Get single work from the works table, or fetch from the internet."""
    pid = normalize_id(string)
    if not pid:
        return None
    try:
        response = (
            pocketbase_client.collection("works").get_first_list_item(f'pid="{pid}"')
        )
    except ClientResponseError as e:
        # if work not found, fetch from the internet
        if e.status == 404:
            work = await fetch_single_work(pid)
            return create_single_work(work)
        return None

    # convert response object to dict
    # rename pid to id and remove fields that are not part of the commonmeta schema
    response = vars(response)
    response = py_.rename_keys(response, {"pid": "id"})
    response = py_.omit(response, "pid", "created", "updated") 
    return compact(response)


def create_single_work(work):
    """Create single work."""

    if not work.get("id", None) or not work.get("type", None):
        return None

    try:
        admin_data
        response = (
            pocketbase_client.collection("works").create(
                {
                    "pid": work.get("id"),
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
                    "archive_locations": work.get("archive_locations", []),
                    "geo_locations": work.get("geo_locations", []),
                    "version": work.get("version", None),
                    "language": work.get("language", None),
                    "additional_type": work.get("additional_type", None),
                    "sizes": work.get("sizes", []),
                    "formats": work.get("formats", []),
                }
            )
        )
    except ClientResponseError as e:
        print(e)
        return None
    
    # return the work, if successful. Create operation returns the id of the created work
    return get_single_work(response.id)


def update_single_work(id, work):
    """Update single work, using the pocketbase id."""

    if not work.get("id", None) or not work.get("type", None):
        return None

    try:
        admin_data
        response = (
            pocketbase_client.collection("works").update(id,
                {
                    "pid": work.get("id"),
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
                    "archive_locations": work.get("archive_locations", []),
                    "geo_locations": work.get("geo_locations", []),
                    "version": work.get("version", None),
                    "language": work.get("language", None),
                    "additional_type": work.get("additional_type", None),
                    "sizes": work.get("sizes", []),
                    "formats": work.get("formats", []),
                }
            )
        )
    except ClientResponseError as e:
        print(e)
        return None
    
    # return the work, if successful. Update operation returns the id of the created work
    return get_single_work(response.get("id"))


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
