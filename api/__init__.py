"""Main quart application"""

from hypercorn.config import Config
import logging
from math import ceil
from os import environ
import pydash as py_
from dotenv import load_dotenv
import frontmatter
from quart import Quart, request, jsonify, redirect
from quart_schema import (
    QuartSchema,
    Info,
    validate_request,
    validate_response,
    hide,
    RequestSchemaValidationError,
)
from quart_rate_limiter import RateLimiter
from quart_cors import cors
from commonmeta import doi_from_url
from quart_db import QuartDB

from api.db_client import Database
from api.utils import (
    get_formatted_metadata,
    get_markdown,
    convert_to_commonmeta,
    write_epub,
    write_pdf,
    write_jats,
    format_markdown,
    validate_uuid,
    format_datetime,
    format_authors,
    format_authors_full,
    format_authors_with_orcid,
    format_license,
    format_relationships,
    translate_titles,
)
from api.posts import (
    extract_all_posts,
    extract_all_posts_by_blog,
    update_all_posts,
    update_all_posts_by_blog,
    update_all_unclassified_posts_by_blog,
    extract_single_post,
    update_single_post,
    delete_draft_record,
    delete_all_draft_records,
    update_all_cited_posts,
)
from api.blogs import extract_single_blog, extract_all_blogs
from api.citations import extract_all_citations, extract_all_citations_by_prefix
from api.schema import Blog, Citation, Post, PostQuery

SERVICE_ROLE_KEY_ENV = "ROGUE_SCHOLAR_SERVICE_ROLE_KEY"
LEGACY_SERVICE_ROLE_KEY_ENV = "QUART_SUPABASE_SERVICE_ROLE_KEY"


def _get_service_role_key() -> str | None:
    return environ.get(SERVICE_ROLE_KEY_ENV) or environ.get(LEGACY_SERVICE_ROLE_KEY_ENV)


def _is_authorized() -> bool:
    expected_key = _get_service_role_key()
    if not expected_key:
        return False

    authorization = request.headers.get("Authorization")
    if not authorization:
        return False

    parts = authorization.split(" ", 1)
    if len(parts) != 2:
        return False

    scheme, token = parts[0], parts[1]
    if scheme.lower() != "bearer":
        return False

    return token == expected_key


def _typesense_like_search_response(
    *,
    items: list[dict],
    found: int,
    page: int,
    per_page: int,
    include_fields: list[str] | None = None,
) -> dict:
    if include_fields:
        include_fields_set = set(include_fields)
        items = [
            {k: v for k, v in item.items() if k in include_fields_set} for item in items
        ]

    return {
        "found": found,
        "out_of": found,
        "page": page,
        "per_page": per_page,
        "hits": [{"document": item} for item in items],
        "total-results": found,
        "items": items,
    }


config = Config()
config.from_toml("hypercorn.toml")
load_dotenv()
logger = logging.getLogger(__name__)
version = "0.16"  # TODO: importlib.metadata.version('rogue-scholar-api')

app = Quart(__name__, static_folder="static", static_url_path="")
app.config.from_prefixed_env()
QuartSchema(app, info=Info(title="Rogue Scholar API", version=version))
limiter = RateLimiter(app)
app = cors(app, allow_origin="*")

# QuartDB PostgreSQL connection
#
# We intentionally disable QuartDB's auto-migration feature for this app.
# The project does not ship QuartDB migrations, and some existing databases
# can have legacy `schema_migration` state tables that trigger QuartDB's
# migration compatibility path during ASGI lifespan startup.
db = QuartDB(
    app,
    url=f"postgresql+psycopg://{environ['QUART_POSTGRES_USER']}:{environ['QUART_POSTGRES_PASSWORD']}@{environ['QUART_POSTGRES_HOST']}:{environ.get('QUART_POSTGRES_PORT', '5432')}/{environ['QUART_POSTGRES_DB']}",
    migrations_folder=None,
    data_path=None,
)


def run() -> None:
    """Run the app."""
    app.run(host="0.0.0.0", port=5200)


@app.route("/")
@hide
def default():
    """Redirect / to /posts."""
    return redirect("/posts", code=301)


@app.route("/heartbeat")
async def heartbeat():
    """Heartbeat."""
    return "OK", 200


@app.route("/blogs/")
@hide
async def blogs_redirect():
    """Redirect /blogs/ to /blogs."""
    return redirect("/blogs", code=301)


@validate_response(Blog)
@app.route("/blogs")
async def blogs():
    """Search blogs by query, category, generator, language.
    Options to change page, per_page and include fields."""
    query = request.args.get("query") or ""
    page = int(request.args.get("page") or "1")

    status = ["active", "archived", "expired"]
    start_page = page if page and page > 0 else 1
    offset = (start_page - 1) * 10
    limit = 10

    try:
        # Get count
        count_query = """
            SELECT COUNT(*) as count
            FROM blogs
            WHERE status = ANY(:statuses)
            AND title ILIKE :title_pattern
        """
        count_result = await Database.fetch_one(
            count_query, {"statuses": status, "title_pattern": f"%{query}%"}
        )
        total_count = count_result["count"] if count_result else 0

        # Get data
        data_query = """
            SELECT slug, title, description, language, favicon, feed_url,
                   feed_format, home_page_url, generator, category, subfield
            FROM blogs
            WHERE status = ANY(:statuses)
            AND title ILIKE :title_pattern
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """
        items = await Database.fetch_all(
            data_query,
            {
                "statuses": status,
                "title_pattern": f"%{query}%",
                "limit": limit,
                "offset": offset,
            },
        )
        return jsonify({"total-results": total_count, "items": items})
    except Exception as e:
        logger.warning(e.args[0] if hasattr(e, "args") else str(e))
        return {"error": "An error occured."}, 400


@validate_response(Blog)
@app.route("/blogs", methods=["POST"])
async def post_blogs():
    """Update all blogs, using information from the blogs' feed."""

    if not _is_authorized():
        return {"error": "Unauthorized."}, 401
    else:
        result = await extract_all_blogs()
        return jsonify(result)


@validate_response(Blog)
@app.route("/blogs/<slug>")
async def blog(slug):
    """Get blog by slug."""
    query = """
        SELECT b.id, b.slug, b.feed_url, b.current_feed_url, b.home_page_url,
               b.archive_host, b.archive_collection, b.archive_timestamps,
               b.feed_format, b.created_at, b.updated_at, b.registered_at,
               b.license, b.mastodon, b.generator, b.generator_raw, b.language,
               b.favicon, b.title, b.description, b.category, b.subfield,
               b.status, b.user_id, b.authors, b.use_api, b.relative_url,
               b.filter, b.secure, b.community_id, b.prefix, b.issn,
               json_agg(
                   json_build_object(
                       'id', p.id,
                       'guid', p.guid,
                       'doi', p.doi,
                       'url', p.url,
                       'title', p.title,
                       'summary', p.summary,
                       'published_at', p.published_at,
                       'updated_at', p.updated_at
                   )
               ) FILTER (WHERE p.id IS NOT NULL) as posts
        FROM blogs b
        LEFT JOIN posts p ON b.slug = p.blog_slug
        WHERE b.slug = :slug
        GROUP BY b.id, b.slug, b.feed_url, b.current_feed_url, b.home_page_url,
                 b.archive_host, b.archive_collection, b.archive_timestamps,
                 b.feed_format, b.created_at, b.updated_at, b.registered_at,
                 b.license, b.mastodon, b.generator, b.generator_raw, b.language,
                 b.favicon, b.title, b.description, b.category, b.subfield,
                 b.status, b.user_id, b.authors, b.use_api, b.relative_url,
                 b.filter, b.secure, b.community_id, b.prefix, b.issn
    """
    result = await Database.fetch_one(query, {"slug": slug})
    if not result:
        return {"error": "Blog not found"}, 404
    return jsonify(result)


@validate_response(Blog)
@app.route("/blogs/<slug>", methods=["POST"])
async def post_blog(slug):
    """Update blog by slug, using information from the blog's feed.
    Create InvenioRDM entry for the blog."""
    if not _is_authorized():
        return {"error": "Unauthorized."}, 401

    result = await extract_single_blog(slug)
    return jsonify(result)


@validate_response(Blog)
@app.route("/blogs/<slug>/<suffix>", methods=["POST"])
async def post_blog_posts(slug: str, suffix: str | None = None):
    """Update blog posts by slug."""

    page = int(request.args.get("page") or "1")
    update = request.args.get("update")
    validate = request.args.get("validate")
    classify = request.args.get("classify")

    if not _is_authorized():
        return {"error": "Unauthorized."}, 401
    elif slug and suffix == "posts":
        try:
            if update == "self":
                result = await update_all_posts_by_blog(
                    slug,
                    page=page,
                    validate_all=(validate == "all"),
                    classify_all=(classify == "all"),
                )
            elif update == "unclassified":
                result = await update_all_unclassified_posts_by_blog(
                    slug,
                    page=page,
                    validate_all=(validate == "all"),
                    classify_all=(classify == "all"),
                )
            else:
                result = await extract_all_posts_by_blog(
                    slug,
                    page=page,
                    update_all=(update == "all"),
                    validate_all=(validate == "all"),
                    classify_all=(classify == "all"),
                )
            if isinstance(result, dict) and result.get("error", None):
                return result, 400
            return jsonify(result)
        except Exception as e:
            logger.warning(e.args[0])
            return {"error": "An error occured."}, 400
    else:
        return {"error": "An error occured."}, 400


@app.route("/citations/")
@hide
async def citations_redirect():
    """Redirect /citations/ to /citations."""
    return redirect("/citations", code=301)


@validate_response(Citation)
@app.route("/citations")
async def citations():
    """Show citations.
    Options to change page."""
    page = int(request.args.get("page") or "1")
    type_ = request.args.get("type")
    blog_slug = request.args.get("blog_slug")

    start_page = page if page and page > 0 else 1
    offset = (start_page - 1) * 10
    limit = 10

    try:
        # Build WHERE conditions dynamically
        where_conditions = []
        params = {"limit": limit, "offset": offset}

        if blog_slug:
            where_conditions.append("c.blog_slug = :blog_slug")
            params["blog_slug"] = blog_slug
        if type_:
            where_conditions.append("c.type = :type")
            params["type"] = type_

        where_clause = (
            "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        )

        # Get count
        count_query = f"""
            SELECT COUNT(*) as count
            FROM citations c
            {where_clause}
        """
        count_result = await Database.fetch_one(count_query, params)
        total_count = count_result["count"] if count_result else 0

        # Get data with DOI info
        data_query = f"""
            SELECT c.citation, c.unstructured, c.validated, c.updated_at, c.published_at,
                   c.doi, c.cid, c.blog_slug, c.type
            FROM citations c
            {where_clause}
            ORDER BY c.published_at DESC
            LIMIT :limit OFFSET :offset
        """
        items = await Database.fetch_all(data_query, params)
        return jsonify({"total-results": total_count, "items": items})
    except Exception as e:
        logger.warning(e.args[0] if hasattr(e, "args") else str(e))
        return {"error": "An error occured."}, 400


@validate_response(Citation)
@app.route("/citations/<slug>/<suffix>")
async def citation(slug: str, suffix: str):
    """Get citation by doi."""
    if slug and suffix:
        doi = f"https://doi.org/{slug}/{suffix}"
        query = """
            SELECT citation, unstructured, validated, updated_at, published_at
            FROM citations
            WHERE doi = :doi
            ORDER BY published_at ASC, updated_at DESC
        """
        items = await Database.fetch_all(query, {"doi": doi})
        return jsonify(items)
    else:
        return {"error": "An error occured."}, 400


@validate_response(Citation)
@app.route("/citations", methods=["POST"])
async def post_citations():
    """Upsert all citations."""
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
        "10.64395",
        "10.65527",
    ]
    if not _is_authorized():
        return {"error": "Unauthorized."}, 401

    try:
        result = await extract_all_citations()
        return jsonify(result)
    except Exception as e:
        logger.warning(e.args[0])
        return {"error": "An error occured."}, 400


@validate_response(Citation)
@app.route("/citations/<slug>", methods=["POST"])
@app.route("/citations/<slug>/<suffix>", methods=["POST"])
async def post_citations_by_prefix(slug: str, suffix: str | None = None):
    """Upsert citations by prefix."""
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
        "10.64395",
        "10.65527",
    ]
    if slug not in prefixes:
        logger.warning(f"Invalid prefix: {slug}")
        return {"error": "An error occured."}, 400

    if not _is_authorized():
        return {"error": "Unauthorized."}, 401

    try:
        if suffix:
            slug = f"{slug}/{suffix}"
        result = await extract_all_citations_by_prefix(slug)
        return jsonify(result)
    except Exception as e:
        logger.warning(e.args[0])
        return {"error": "An error occured."}, 400


@app.route("/posts/")
@hide
async def posts_redirect():
    """Redirect /posts/ to /posts."""
    return redirect("/posts", code=301)


@validate_request(PostQuery)
@validate_response(Post)
@app.route("/posts")
async def posts():
    """Search posts by query, category, flag. Options to change page, per_page."""
    preview = request.args.get("preview")
    query = request.args.get("query") or ""
    language = request.args.get("language")
    include_fields = request.args.get("include_fields")
    include_fields_list = (
        [f.strip() for f in include_fields.split(",") if f.strip()]
        if include_fields
        else None
    )
    per_page = int(request.args.get("per_page") or "10")
    per_page = min(per_page, 50)
    page = int(request.args.get("page") or "1")
    blog_slug = request.args.get("blog_slug")
    status = ["active", "archived", "expired"]
    if preview:
        status = ["pending", "active", "archived", "expired"]
    start_page = page if page and page > 0 else 1
    offset = (start_page - 1) * per_page

    try:
        # Build WHERE conditions
        where_conditions = ["p.status = ANY(:statuses)", "p.title ILIKE :title_pattern"]
        params = {
            "statuses": status,
            "title_pattern": f"%{query}%",
            "limit": per_page,
            "offset": offset,
        }

        if blog_slug:
            where_conditions.append("p.blog_slug = :blog_slug")
            params["blog_slug"] = blog_slug

        if language:
            where_conditions.append("p.language = :language")
            params["language"] = language

        where_clause = "WHERE " + " AND ".join(where_conditions)

        # Get count
        count_query = f"""
            SELECT COUNT(*) as count
            FROM posts p
            {where_clause}
        """
        count_result = await Database.fetch_one(count_query, params)
        total_count = count_result["count"] if count_result else 0

        # Get data with blog info
        data_query = f"""
            SELECT p.id, p.guid, p.doi, p.parent_doi, p.url, p.archive_url,
                   p.title, p.summary, p.abstract, p.published_at, p.updated_at,
                   p.registered_at, p.indexed_at, p.indexed, p.authors, p.image,
                   p.tags, p.language, p.reference, p.relationships,
                   p.funding_references, p.blog_name, p.blog_slug, p.content_html,
                   p.rid, p.version, p.status,
                   row_to_json(b.*) as blog
            FROM posts p
            INNER JOIN blogs b ON p.blog_slug = b.slug
            {where_clause}
            ORDER BY p.published_at DESC
            LIMIT :limit OFFSET :offset
        """
        items = await Database.fetch_all(data_query, params)
        return jsonify(
            _typesense_like_search_response(
                items=items,
                found=total_count,
                page=start_page,
                per_page=per_page,
                include_fields=include_fields_list,
            )
        )
    except Exception as e:
        logger.warning(e.args[0] if hasattr(e, "args") else str(e))
        return {"error": "An error occured."}, 400


@app.route("/posts", methods=["POST"])
async def post_posts():
    """Update posts."""

    page = int(request.args.get("page") or "1")
    update = request.args.get("update")
    validate = request.args.get("validate")
    classify = request.args.get("classify")

    if not _is_authorized():
        return {"error": "Unauthorized."}, 401
    else:
        try:
            if update == "cited":
                updated_posts = await update_all_cited_posts(page=page)
                return jsonify(updated_posts)
            elif update == "self":
                updated_posts = await update_all_posts(page=page)
                return jsonify(updated_posts)
            else:
                extracted_posts = await extract_all_posts(
                    page=page,
                    update_all=(update == "all"),
                    validate_all=(validate == "all"),
                    classify_all=(classify == "all"),
                )
                return jsonify(extracted_posts)
        except Exception as e:
            logger.warning(e)
            return {"error": "An error occured."}, 400


@validate_response(Post)
@app.route("/posts/<slug>", methods=["POST"])
@app.route("/posts/<slug>/<suffix>", methods=["POST"])
async def post_post(slug: str, suffix: str | None = None):
    """Update post by either uuid or doi, using information from the blog's feed."""

    update = request.args.get("update")
    validate = request.args.get("validate")
    classify = request.args.get("classify")
    previous = request.args.get("previous")
    if not _is_authorized():
        return {"error": "Unauthorized."}, 401

    try:
        if update == "self":
            result = await update_single_post(
                slug,
                suffix=suffix,
                validate_all=(validate == "all"),
                classify_all=(classify == "all"),
                previous=previous,
            )
            return jsonify(result)
        else:
            result = await extract_single_post(
                slug,
                suffix=suffix,
                validate_all=(validate == "all"),
                classify_all=(classify == "all"),
                previous=previous,
            )
            return jsonify(result)
    except Exception as e:
        logger.warning(e.args[0])
        return {"error": "An error occured."}, 400


@validate_response(Post)
@app.route("/posts/<slug>")
@app.route("/posts/<slug>/<suffix>")
@app.route("/posts/<slug>/<suffix>/<relation>")
async def post(slug: str, suffix: str | None = None, relation: str | None = None):
    """Get post by slug."""
    prefixes = [
        "10.13003",
        "10.34732",  # not managed by Front Matter
        "10.53731",
        "10.54900",
        "10.57689",  # not managed by Front Matter
        "10.58079",  # not managed by Front Matter
        "10.59347",
        "10.59348",
        "10.59349",
        "10.59350",
        "10.63485",
        "10.63517",
        "10.64000",
        "10.64395",
        "10.65527",
        "10.71938",
        "10.83132",
    ]
    permitted_slugs = [
        "unregistered",
        "updated",
        "waiting",
        "cited",
    ] + prefixes
    status = ["active", "archived", "expired"]
    if slug not in permitted_slugs and not validate_uuid(slug):
        logger.warning(f"Invalid slug: {slug}")
        return {"error": "An error occured."}, 400
    format_ = request.args.get("format") or "json"
    locale = request.args.get("locale") or "en-US"
    style = request.args.get("style") or "apa"
    page = int(request.args.get("page") or "1")
    per_page = int(request.args.get("per_page") or "50")
    if slug == "unregistered":
        query = """
            SELECT COUNT(*) as count
            FROM posts p
            INNER JOIN blogs b ON p.blog_slug = b.slug
            WHERE b.prefix IS NOT NULL
            AND p.doi IS NULL
            AND p.rid IS NULL
            AND p.status = ANY(:statuses)
        """
        count_result = await Database.fetch_one(query, {"statuses": status})
        total_count = count_result["count"] if count_result else 0

        data_query = """
            SELECT p.id, p.guid, p.doi, p.url, p.archive_url, p.title, p.summary,
                   p.abstract, p.content_html, p.published_at, p.updated_at,
                   p.registered_at, p.indexed_at, p.authors, p.image, p.tags,
                   p.language, p.reference, p.relationships, p.funding_references,
                   p.blog_name, p.blog_slug, p.rid,
                   row_to_json(b.*) as blog
            FROM posts p
            INNER JOIN blogs b ON p.blog_slug = b.slug
            WHERE b.prefix IS NOT NULL
            AND p.doi IS NULL
            AND p.rid IS NULL
            AND p.status = ANY(:statuses)
            ORDER BY p.published_at DESC
            LIMIT :limit
        """
        items = await Database.fetch_all(
            data_query, {"statuses": status, "limit": min(per_page, 50)}
        )
        return jsonify(items)
    elif slug == "updated":
        query = """
            SELECT COUNT(*) as count
            FROM posts p
            INNER JOIN blogs b ON p.blog_slug = b.slug
            WHERE b.prefix IS NOT NULL
            AND p.updated = true
            AND p.doi IS NOT NULL
            AND p.status = ANY(:statuses)
        """
        count_result = await Database.fetch_one(query, {"statuses": status})
        total_count = count_result["count"] if count_result else 0

        data_query = """
            SELECT p.id, p.guid, p.doi, p.url, p.archive_url, p.title, p.summary,
                   p.abstract, p.content_html, p.published_at, p.updated_at,
                   p.registered_at, p.indexed_at, p.authors, p.image, p.tags,
                   p.language, p.reference, p.relationships, p.funding_references,
                   p.blog_name, p.blog_slug, p.rid,
                   row_to_json(b.*) as blog
            FROM posts p
            INNER JOIN blogs b ON p.blog_slug = b.slug
            WHERE b.prefix IS NOT NULL
            AND p.updated = true
            AND p.doi IS NOT NULL
            AND p.status = ANY(:statuses)
            ORDER BY p.updated_at DESC
            LIMIT :limit
        """
        items = await Database.fetch_all(
            data_query, {"statuses": status, "limit": min(per_page, 50)}
        )
        return jsonify(items)
    elif slug == "waiting":
        query = """
            SELECT COUNT(*) as count
            FROM posts p
            INNER JOIN blogs b ON p.blog_slug = b.slug
            WHERE b.prefix IS NOT NULL
            AND p.indexed_at <= 1
            AND p.status = ANY(:statuses)
        """
        count_result = await Database.fetch_one(query, {"statuses": status})
        total_count = count_result["count"] if count_result else 0

        data_query = """
            SELECT p.id, p.guid, p.doi, p.url, p.archive_url, p.title, p.summary,
                   p.abstract, p.content_html, p.published_at, p.updated_at,
                   p.registered_at, p.indexed_at, p.authors, p.image, p.tags,
                   p.language, p.reference, p.relationships, p.funding_references,
                   p.blog_name, p.blog_slug, p.rid,
                   row_to_json(b.*) as blog
            FROM posts p
            INNER JOIN blogs b ON p.blog_slug = b.slug
            WHERE b.prefix IS NOT NULL
            AND p.indexed_at <= 1
            AND p.status = ANY(:statuses)
            ORDER BY p.published_at DESC
            LIMIT :limit
        """
        items = await Database.fetch_all(
            data_query, {"statuses": status, "limit": min(per_page, 50)}
        )
        return jsonify({"total-results": total_count, "items": items})
    elif slug == "cited":
        # Get total count first
        count_query = """
            SELECT COUNT(DISTINCT p.id) as count
            FROM posts p
            INNER JOIN citations c ON p.doi = c.doi
            WHERE p.doi IS NOT NULL
        """
        count_result = await Database.fetch_one(count_query)
        total = count_result["count"] if count_result else 0
        total_pages = ceil(total / 50)
        page = min(page, total_pages)
        start_page = (page - 1) * 50 if page > 0 else 0

        data_query = """
            SELECT p.id, p.guid, p.doi, p.parent_doi, p.url, p.archive_url,
                   p.title, p.summary, p.abstract, p.published_at, p.updated_at,
                   p.registered_at, p.indexed_at, p.indexed, p.authors, p.image,
                   p.tags, p.language, p.reference, p.relationships,
                   p.funding_references, p.blog_name, p.blog_slug, p.content_html,
                   p.rid, p.version,
                   row_to_json(b.*) as blog,
                   (
                       SELECT json_agg(row_to_json(c.*))
                       FROM citations c
                       WHERE c.doi = p.doi AND c.cid IS NOT NULL
                   ) as citations
            FROM posts p
            INNER JOIN blogs b ON p.blog_slug = b.slug
            WHERE b.prefix IS NOT NULL
            AND p.doi IS NOT NULL
            ORDER BY p.updated_at DESC
            LIMIT :limit OFFSET :offset
        """
        items = await Database.fetch_all(
            data_query, {"limit": min(per_page, 100), "offset": start_page}
        )
        return jsonify({"total-results": total, "items": items})
    elif slug in prefixes and suffix and relation:
        if validate_uuid(slug):
            query = """
                SELECT reference
                FROM posts
                WHERE id = :id
            """
            result = await Database.fetch_one(query, {"id": slug})
        else:
            doi = f"https://doi.org/{slug}/{suffix.lower()}"
            query = """
                SELECT reference
                FROM posts
                WHERE doi = :doi
            """
            result = await Database.fetch_one(query, {"doi": doi})
        references = result.get("reference", []) if result else []
        if isinstance(references, list):
            normalized_references = []
            for idx, ref in enumerate(references, start=1):
                if isinstance(ref, dict) and "key" not in ref:
                    ref = {"key": f"ref{idx}", **ref}
                if (
                    isinstance(ref, dict)
                    and "title" not in ref
                    and isinstance(ref.get("unstructured"), str)
                ):
                    parts = [
                        p.strip() for p in ref["unstructured"].split(".") if p.strip()
                    ]
                    if len(parts) >= 2:
                        ref = {**ref, "title": parts[1]}
                if (
                    isinstance(ref, dict)
                    and "publicationYear" not in ref
                    and isinstance(ref.get("unstructured"), str)
                ):
                    import re

                    match = re.search(r"\b(19|20)\d{2}\b", ref["unstructured"])
                    if match:
                        ref = {**ref, "publicationYear": match.group(0)}
                normalized_references.append(ref)
            references = normalized_references
        count = len(references)
        return jsonify({"total-results": count, "items": references})
    elif slug in prefixes and suffix:
        path = suffix.split(".")
        if len(path) > 1 and path[-1] in [
            "md",
            "epub",
            "pdf",
            "xml",
            "bib",
            "ris",
            "jsonld",
        ]:
            format_ = path.pop()
            suffix = ".".join(path)
        if format_ == "bib":
            format_ = "bibtex"
        elif format_ == "jsonld":
            format_ = "schema_org"
    try:
        if validate_uuid(slug):
            # Try with citations first
            query = """
                SELECT p.id, p.guid, p.doi, p.parent_doi, p.url, p.archive_url,
                       p.title, p.summary, p.abstract, p.published_at, p.updated_at,
                       p.registered_at, p.indexed_at, p.indexed, p.authors, p.image,
                       p.tags, p.language, p.reference, p.relationships,
                       p.funding_references, p.blog_name, p.blog_slug, p.content_html,
                       p.rid, p.version,
                       row_to_json(b.*) as blog,
                       (
                           SELECT json_agg(row_to_json(c.*))
                           FROM citations c
                           WHERE c.doi = p.doi AND c.cid IS NOT NULL
                       ) as citations
                FROM posts p
                INNER JOIN blogs b ON p.blog_slug = b.slug
                WHERE p.id = :id
            """
            result = await Database.fetch_one(query, {"id": slug})
            if not result:
                # Fallback without citations
                query = """
                    SELECT p.id, p.guid, p.doi, p.parent_doi, p.url, p.archive_url,
                           p.title, p.summary, p.abstract, p.published_at, p.updated_at,
                           p.registered_at, p.indexed_at, p.indexed, p.authors, p.image,
                           p.tags, p.language, p.reference, p.relationships,
                           p.funding_references, p.blog_name, p.blog_slug, p.content_html,
                           p.rid, p.version,
                           row_to_json(b.*) as blog
                    FROM posts p
                    INNER JOIN blogs b ON p.blog_slug = b.slug
                    WHERE p.id = :id
                """
                result = await Database.fetch_one(query, {"id": slug})
            basename = slug
        else:
            doi = f"https://doi.org/{slug}/{suffix}"
            # Try with citations first
            query = """
                SELECT p.id, p.guid, p.doi, p.parent_doi, p.url, p.archive_url,
                       p.title, p.summary, p.abstract, p.published_at, p.updated_at,
                       p.registered_at, p.indexed_at, p.indexed, p.authors, p.image,
                       p.tags, p.language, p.reference, p.relationships,
                       p.funding_references, p.blog_name, p.blog_slug, p.content_html,
                       p.rid, p.version,
                       row_to_json(b.*) as blog,
                       (
                           SELECT json_agg(row_to_json(c.*))
                           FROM citations c
                           WHERE c.doi = p.doi AND c.cid IS NOT NULL
                       ) as citations
                FROM posts p
                INNER JOIN blogs b ON p.blog_slug = b.slug
                WHERE p.doi = :doi
            """
            result = await Database.fetch_one(query, {"doi": doi})
            if not result:
                # Fallback without citations
                query = """
                    SELECT p.id, p.guid, p.doi, p.parent_doi, p.url, p.archive_url,
                           p.title, p.summary, p.abstract, p.published_at, p.updated_at,
                           p.registered_at, p.indexed_at, p.indexed, p.authors, p.image,
                           p.tags, p.language, p.reference, p.relationships,
                           p.funding_references, p.blog_name, p.blog_slug, p.content_html,
                           p.rid, p.version,
                           row_to_json(b.*) as blog
                    FROM posts p
                    INNER JOIN blogs b ON p.blog_slug = b.slug
                    WHERE p.doi = :doi
                """
                result = await Database.fetch_one(query, {"doi": doi})
            basename = doi_from_url(doi).replace("/", "-")

        if not result:
            return {"error": "Post not found"}, 404
        content = result.get("content_html", None) if result else None
        if format_ == "json":
            return jsonify(result)
        metadata = py_.omit(result, ["content_html"]) if result else None
        meta = convert_to_commonmeta(metadata)
        if isinstance(meta, dict):
            meta["type"] = "article"
    except Exception as e:
        logger.warning(e.args[0])
        return {"error": "Post not found"}, 404
    if format_ in ["md", "epub", "pdf", "xml"]:
        metadata = py_.rename_keys(
            metadata,
            {
                "authors": "author",
                "blog_name": "container",
                "doi": "identifier",
                "language": "lang",
                "published_at": "date",
                "reference:": "references",
                "tags": "keywords",
                "updated_at": "date_updated",
                "blog.issn": "issn",
                "blog.license": "license",
            },
        )
        metadata = py_.omit(
            metadata,
            ["id", "blog_slug", "indexed_at"],
        )
        markdown = format_markdown(get_markdown(content), metadata)
        if format_ == "epub":
            markdown["date"] = format_datetime(markdown["date"], markdown["lang"])
            markdown["author"] = format_authors(markdown["author"])
            markdown["rights"] = None
            markdown = frontmatter.dumps(markdown)
            epub = write_epub(markdown)
            return (
                epub,
                200,
                {
                    "Content-Type": "application/epub+zip",
                    "Content-Disposition": f"attachment; filename={basename}.epub",
                },
            )
        elif format_ == "pdf":
            markdown["author"] = format_authors_with_orcid(markdown["author"])
            markdown["license"] = {
                "text": format_license(
                    markdown["author"], markdown["date"], markdown["rights"]
                ),
                "id": "cc-by"
                if markdown["rights"]
                == "https://creativecommons.org/licenses/by/4.0/legalcode"
                else None,
                "link": markdown["rights"],
            }
            markdown["date"] = format_datetime(markdown["date"], markdown["lang"])
            citation = get_formatted_metadata(meta, "citation", style, locale)
            if citation:
                markdown["citation"] = citation["data"]
            else:
                markdown["citation"] = markdown["identifier"]
            markdown["relationships"] = format_relationships(markdown["relationships"])
            markdown = translate_titles(markdown)
            image = markdown.get("image", None)

            markdown = frontmatter.dumps(markdown)
            content, error = write_pdf(markdown)
            if error is not None:
                logger.error(error)
            # with pikepdf.open(BytesIO(content)) as pdf:
            #     memfilespec = AttachedFileSpec(
            #         pdf, markdown.encode("utf-8"), mime_type="text/markdown"
            #     )
            #     pdf.attachments[f"{basename}.md"] = memfilespec
            #     if image:
            #         image_bytes = download_image(image)
            #         if image_bytes:
            #             img_ext = get_extension_from_url(image)
            #             if img_ext not in ["jpg", "jpeg", "png", "gif", "svg", "webp"]:
            #                 img_ext = "bin"
            #             img_memfilespec = AttachedFileSpec(
            #                 pdf,
            #                 image_bytes,
            #                 mime_type=f"image/{img_ext}",
            #             )
            #             pdf.attachments[f"image.{img_ext}"] = img_memfilespec
            #     output = BytesIO()
            #     pdf.save(output)
            #     pdf_bytes = output.getvalue()
            return (
                content,
                200,
                {
                    "Content-Type": "application/pdf",
                    "Content-Disposition": f"attachment; filename={basename}.pdf",
                },
            )
        elif format_ == "xml":
            markdown["author"] = format_authors_full(markdown["author"])
            markdown["date"] = {
                "iso-8601": markdown["date"],
                "year": markdown["date"][:4],
                "month": markdown["date"][5:7],
                "day": markdown["date"][8:10],
            }
            markdown["article"] = {"doi": markdown["identifier"]}
            markdown["license"] = {
                "text": "Creative Commons Attribution 4.0",
                "type": "open-access",
                "link": markdown["rights"],
            }
            markdown["journal"] = {"title": markdown["container"]}
            markdown = frontmatter.dumps(markdown)
            jats = write_jats(markdown)
            return (
                jats,
                200,
                {
                    "Content-Type": "application/xml",
                    "Content-Disposition": f"attachment; filename={basename}.xml",
                },
            )
        else:
            return (
                frontmatter.dumps(markdown),
                200,
                {
                    "Content-Type": "text/markdown;charset=UTF-8",
                    "Content-Disposition": f"attachment; filename={basename}.md",
                },
            )
    elif format_ in [
        "bibtex",
        "ris",
        "csl",
        "schema_org",
        "datacite",
        "crossref_xml",
        "commonmeta",
        "citation",
    ]:
        response = get_formatted_metadata(meta, format_, style, locale)
        if not response:
            logger.warning("Metadata not found")
            return {"error": "Metadata not found."}, 404
        return (response["data"], 200, response["options"])
    else:
        return {"error": "Post not found"}, 404


@app.route("/records", methods=["DELETE"])
async def delete_all_records():
    """Delete all_InvenioRDM draft records."""
    if not _is_authorized():
        return {"error": "Unauthorized."}, 401

    try:
        result = await delete_all_draft_records()
        return jsonify(result)
    except Exception as e:
        logger.warning(e.args[0] if hasattr(e, "args") else str(e))
        return {"error": "An error occured."}, 400


@app.route("/records/<slug>", methods=["DELETE"])
async def delete_record(slug: str):
    """Delete InvenioRDM draft record using the rid."""
    if not _is_authorized():
        return {"error": "Unauthorized."}, 401
    try:
        result = await delete_draft_record(slug)
        return jsonify(result)
    except Exception as e:
        logger.warning(e.args[0])
        return {"error": "An error occured."}, 400


@app.errorhandler(RequestSchemaValidationError)
async def handle_request_validation_error():
    return {"error": "VALIDATION"}, 400


@app.errorhandler(429)
async def ratelimit_handler(e):
    return (
        jsonify(
            {
                "error": "Too Many Requests",
                "detail": "Rate limit exceeded. Please retry later.",
            }
        ),
        429,
        {"retry-after": str(e.retry_after)},  # number of seconds to wait
    )
