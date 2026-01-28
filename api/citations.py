"""Citations module."""

from os import environ, path
import yaml
import httpx
import xmltodict
import asyncio
import pydash as py_
from datetime import datetime, timezone
from commonmeta import (
    validate_doi,
    normalize_doi,
    doi_from_url,
    wrap,
    Metadata,
    compact,
)

from api.db_client import Database, PostsQueries, CitationsQueries

# from api.supabase_client import (
#     supabase_client as supabase,
#     supabase_admin_client as supabase_admin,
# )

from api.posts import (
    update_single_post,
)


async def extract_all_citations_by_prefix(slug: str) -> list:
    """Extract all citations from Crossref cited-by service by slug (prefix or doi). Needs username and password for account
    managing the prefix."""
    username = environ.get("QUART_CROSSREF_USERNAME_WITH_ROLE", None)
    password = environ.get("QUART_CROSSREF_PASSWORD", None)
    if not username or not password or not slug:
        return []
    url = f"https://doi.crossref.org/servlet/getForwardLinks?usr={username}&pwd={password}&doi={slug}&startDate=2000-01-01&include_postedcontent=true"
    response = httpx.get(url, headers={"Accept": "text/xml;charset=utf-8"}, timeout=10)
    response.raise_for_status()
    crossref_result = xmltodict.parse(response.text)
    citations = py_.get(
        crossref_result, "crossref_result.query_result.body.forward_link", []
    )
    print(f"Upserting {len(wrap(citations))} citations for {slug}")
    return await upsert_citations(wrap(citations))


async def extract_all_citations() -> list:
    """Extract all citations from Crossref cited-by service. Needs username and password for account
    managing the prefix."""
    username = environ.get("QUART_CROSSREF_USERNAME_WITH_ROLE", None)
    password = environ.get("QUART_CROSSREF_PASSWORD", None)
    if not username or not password:
        return []

    prefixes = [
        "10.13003",
        "10.53731",
        "10.54900",
        "10.59347",
        "10.59348",
        "10.59349",
        "10.59350",
        "10.63485",
        "10.63517",
        "10.64000",
        "10.65527",
    ]
    citations = await asyncio.gather(
        *[extract_all_citations_by_prefix(prefix) for prefix in prefixes]
    )
    print(f"Upserting {len(wrap(citations))} citations.")
    return await upsert_citations(wrap(citations))


def parse_crossref_xml(xml: str | None, **kwargs) -> list:
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


async def format_crossref_citation(citation: dict, redirects: dict) -> dict:
    """Format Crossref citation from Crossref cited-by service.
    Citing doi is embedded in different metadata, depending on the content type, e.g. journal_cite, book_cite, etc.
    Some Rogue Scholar DOIs are redirected to new DOIs, which are stored in the redirects.yaml file."""

    cited_doi = validate_doi(citation.get("@doi", None))
    cited_doi = redirects.get(cited_doi, cited_doi)

    citing_doi = validate_doi(
        py_.get(citation, "journal_cite.doi.#text")
        or py_.get(citation, "book_cite.doi.#text")
        or py_.get(citation, "postedcontent_cite.doi.#text")
        or py_.get(citation, "conf_cite.doi.#text")
    )

    if cited_doi is None or citing_doi is None:
        return {}
    cited_doi = cited_doi.lower()
    citing_doi = citing_doi.lower()

    # generate unique identifier using cited_doi and citing_doi
    # TODO: align with OpenCitations OCI identifier

    cid = f"{cited_doi.lower()}::{citing_doi.lower()}"

    # lookup blog_slug for cited doi
    query = """
        SELECT blog_slug
        FROM posts
        WHERE doi = :doi
        LIMIT 1
    """
    result = await Database.fetch_one(query, {"doi": normalize_doi(cited_doi)})
    blog_slug = result.get("blog_slug") if result else None

    # lookup metadata via API call, as we need the publication date to order the citations
    subject = Metadata(citing_doi)

    # subject.write returns bytes, so decode to utf-8 string
    unstructured = subject.write(to="citation", style="apa", locale="en-US").decode(
        "utf-8"
    )
    published_at = py_.get(subject, "date.published")
    type_ = py_.get(subject, "type")
    print(f"Formatting citation {citing_doi} for {cited_doi}")

    return compact(
        {
            "cid": cid,
            "doi": normalize_doi(cited_doi),
            "citation": normalize_doi(citing_doi),
            "unstructured": unstructured,
            "published_at": published_at,
            "type": type_,
            "blog_slug": blog_slug,
        }
    )


async def upsert_citations(citations: list) -> list:
    """Upsert multiple citations."""

    # load redirected dois
    redirects = load_redirects()

    data = [
        await format_crossref_citation(citation, redirects) for citation in citations
    ]
    return [await upsert_single_citation(citation) for citation in data]


async def upsert_single_citation(citation):
    """Upsert single citation."""

    # missing doi, citation or oci
    # oci is used as unique identifier for the citation record
    if not citation.get("doi", None) or not citation.get("citation", None):
        return {}

    try:
        # UPSERT citation using PostgreSQL ON CONFLICT via helper
        data = await CitationsQueries.upsert_citation(
            {
                "cid": citation.get("cid"),
                "doi": citation.get("doi"),
                "citation": citation.get("citation"),
                "unstructured": citation.get("unstructured", None),
                "published_at": citation.get("published_at", None),
                "type": citation.get("type", None),
                "blog_slug": citation.get("blog_slug", None),
            }
        )
        print(
            f"Upserted citation {citation.get('citation')} for doi {citation.get('doi')}"
        )
        if not data:
            return None
        today = datetime.now(timezone.utc).date()
        updated_at_value = data.get("updated_at", None)
        updated_at_dt: datetime | None
        if isinstance(updated_at_value, datetime):
            updated_at_dt = updated_at_value
        elif isinstance(updated_at_value, str):
            updated_at_dt = datetime.fromisoformat(
                updated_at_value.replace("Z", "+00:00")
            )
        else:
            updated_at_dt = None

        # NOTE: We intentionally don't call `update_single_post()` here.
        # The citations endpoint should return citation records, and post-updates
        # can introduce external coupling (and currently still contain legacy code).
        return data
    except Exception as e:
        print(e)
        return None


def load_redirects():
    """Load redirected dois from yaml."""

    file_path = path.join(path.dirname(__file__), "../pandoc/redirects.yaml")
    with open(file_path, encoding="utf-8") as file:
        string = file.read()
        f = yaml.safe_load(string)
        redirects = f[301]
    return redirects
