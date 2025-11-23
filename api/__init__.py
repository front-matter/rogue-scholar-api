"""Main quart application"""

from hypercorn.config import Config
import logging
from datetime import timedelta
from math import ceil
from os import environ
import pydash as py_
from dotenv import load_dotenv
import sentry_sdk
import frontmatter
from quart import g, Quart, request, jsonify, redirect
from quart_schema import (
    QuartSchema,
    Info,
    validate_request,
    validate_response,
    hide,
    RequestSchemaValidationError,
)
from quart_rate_limiter import RateLimiter, RateLimit
from quart_cors import cors
from postgrest import APIError
from commonmeta import doi_from_url
from quart_db import QuartDB

from api.supabase_client import (
    supabase_client,
    blogsSelect,
    blogWithPostsSelect,
    citationsSelect,
    citationsWithDoiSelect,
    postsWithContentSelect,
    postsWithCitationsSelect,
)
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
    extract_single_post,
    update_single_post,
    delete_draft_record,
    delete_all_draft_records,
    update_all_cited_posts,
    update_all_flagged_posts,
)
from api.blogs import extract_single_blog, extract_all_blogs
from api.citations import extract_all_citations, extract_all_citations_by_prefix
from api.schema import Blog, Citation, Post, PostQuery

config = Config()
config.from_toml("hypercorn.toml")
load_dotenv()
rate_limiter = RateLimiter()
logger = logging.getLogger(__name__)
version = "0.16"  # TODO: importlib.metadata.version('rogue-scholar-api')

sentry_sdk.init(
    dsn=environ["QUART_SENTRY_DSN"],
)
app = Quart(__name__, static_folder="static", static_url_path="")
app.config.from_prefixed_env()
QuartSchema(app, info=Info(title="Rogue Scholar API", version=version))
rate_limiter = RateLimiter(app, default_limits=[RateLimit(15, timedelta(seconds=60))])
app = cors(app, allow_origin="*")
# db = QuartDB(
#     app,
#     url=f"postgresql://{environ['QUART_POSTGRES_USER']}:{environ['QUART_POSTGRES_PASSWORD']}@{environ['QUART_POSTGRES_HOST']}/{environ['QUART_POSTGRES_DB']}",
# )


def run() -> None:
    """Run the app."""
    app.run()


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


# @app.get("/test")
# async def get_all():
#     results = await g.connection.fetch_all("SELECT slug FROM blogs")
#     return jsonify([{"slug": row["slug"]} for row in results])


@validate_response(Blog)
@app.route("/blogs")
async def blogs():
    """Search blogs by query, category, generator, language.
    Options to change page, per_page and include fields."""
    query = request.args.get("query") or ""
    page = int(request.args.get("page") or "1")

    status = ["active", "archived", "expired"]
    start_page = page if page and page > 0 else 1
    start_page = (start_page - 1) * 10
    end_page = start_page + 10

    try:
        response = (
            supabase_client.table("blogs")
            .select(blogsSelect, count="exact")
            .in_("status", status)
            .ilike("title", f"%{query}%")
            .order("created_at", desc=True)
            .range(start_page, end_page)
            .execute()
        )
        return jsonify({"total-results": response.count, "items": response.data})
    except APIError as e:
        return {"error": e.message or "An error occured."}, 400


@validate_response(Blog)
@app.route("/blogs", methods=["POST"])
async def post_blogs():
    """Update all blogs, using information from the blogs' feed."""

    if (
        request.headers.get("Authorization", None) is None
        or request.headers.get("Authorization").split(" ")[1]
        != environ["QUART_SUPABASE_SERVICE_ROLE_KEY"]
    ):
        return {"error": "Unauthorized."}, 401
    else:
        result = await extract_all_blogs()
        return jsonify(result)


@validate_response(Blog)
@app.route("/blogs/<slug>")
async def blog(slug):
    """Get blog by slug."""
    response = (
        supabase_client.table("blogs")
        .select(blogWithPostsSelect)
        .eq("slug", slug)
        .maybe_single()
        .execute()
    )
    return jsonify(response.data)


@validate_response(Blog)
@app.route("/blogs/<slug>", methods=["POST"])
async def post_blog(slug):
    """Update blog by slug, using information from the blog's feed.
    Create InvenioRDM entry for the blog."""
    if (
        request.headers.get("Authorization", None) is None
        or request.headers.get("Authorization").split(" ")[1]
        != environ["QUART_SUPABASE_SERVICE_ROLE_KEY"]
    ):
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

    if (
        request.headers.get("Authorization", None) is None
        or request.headers.get("Authorization").split(" ")[1]
        != environ["QUART_SUPABASE_SERVICE_ROLE_KEY"]
    ):
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
    start_page = (start_page - 1) * 10
    end_page = start_page + 10

    try:
        if blog_slug and type_:
            response = (
                supabase_client.table("citations")
                .select(citationsWithDoiSelect, count="exact")
                .eq("blog_slug", blog_slug)
                .eq("type", type_)
                .order("published_at", desc=True)
                .range(start_page, end_page)
                .execute()
            )
        elif blog_slug:
            response = (
                supabase_client.table("citations")
                .select(citationsWithDoiSelect, count="exact")
                .eq("blog_slug", blog_slug)
                .order("published_at", desc=True)
                .range(start_page, end_page)
                .execute()
            )
        elif type_:
            response = (
                supabase_client.table("citations")
                .select(citationsWithDoiSelect, count="exact")
                .eq("type", type_)
                .order("published_at", desc=True)
                .range(start_page, end_page)
                .execute()
            )
        else:
            response = (
                supabase_client.table("citations")
                .select(citationsWithDoiSelect, count="exact")
                .order("published_at", desc=True)
                .range(start_page, end_page)
                .execute()
            )
        return jsonify({"total-results": response.count, "items": response.data})
    except APIError as e:
        return {"error": e.message or "An error occured."}, 400


@validate_response(Citation)
@app.route("/citations/<slug>/<suffix>")
async def citation(slug: str, suffix: str):
    """Get citation by doi."""
    if slug and suffix:
        doi = f"https://doi.org/{slug}/{suffix}"
        response = (
            supabase_client.table("citations")
            .select(citationsSelect)
            .eq("doi", doi)
            .order("published_at", desc=False)
            .order("updated_at", desc=True)
            .execute()
        )
        return jsonify(response.data)
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
        "10.64000",
    ]
    if (
        request.headers.get("Authorization", None) is None
        or request.headers.get("Authorization").split(" ")[1]
        != environ["QUART_SUPABASE_SERVICE_ROLE_KEY"]
    ):
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
        "10.64000",
    ]
    if slug not in prefixes:
        logger.warning(f"Invalid prefix: {slug}")
        return {"error": "An error occured."}, 400

    if (
        request.headers.get("Authorization", None) is None
        or request.headers.get("Authorization").split(" ")[1]
        != environ["QUART_SUPABASE_SERVICE_ROLE_KEY"]
    ):
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
    per_page = int(request.args.get("per_page") or "10")
    per_page = min(per_page, 50)
    page = int(request.args.get("page") or "1")
    blog_slug = request.args.get("blog_slug")
    no_fulltext = request.args.get("no_fulltext")
    status = ["active", "archived", "expired"]
    if preview:
        status = ["pending", "active", "archived", "expired"]
    start_page = page if page and page > 0 else 1
    start_page = (start_page - 1) * per_page
    end_page = start_page + per_page - 1

    try:
        if no_fulltext == "true":
            response = (
                supabase_client.table("posts")
                .select(postsWithContentSelect, count="exact")
                .in_("status", status)
                .is_("content_html", "null")
                .order("published_at", desc=True)
                .range(start_page, end_page)
                .execute()
            )
        elif blog_slug:
            response = (
                supabase_client.table("posts")
                .select(postsWithContentSelect, count="exact")
                .in_("status", status)
                .eq("blog_slug", blog_slug)
                .ilike("title", f"%{query}%")
                .order("published_at", desc=True)
                .range(start_page, end_page)
                .execute()
            )
        else:
            response = (
                supabase_client.table("posts")
                .select(postsWithContentSelect, count="exact")
                .in_("status", status)
                .ilike("title", f"%{query}%")
                .order("published_at", desc=True)
                .range(start_page, end_page)
                .execute()
            )
        return jsonify({"total-results": response.count, "items": response.data})
    except Exception as e:
        logger.warning(e.args[0])
        return {"error": "An error occured."}, 400


@app.route("/posts", methods=["POST"])
async def post_posts():
    """Update posts."""

    page = int(request.args.get("page") or "1")
    update = request.args.get("update")
    validate = request.args.get("validate")
    classify = request.args.get("classify")

    if (
        request.headers.get("Authorization", None) is None
        or request.headers.get("Authorization").split(" ")[1]
        != environ["QUART_SUPABASE_SERVICE_ROLE_KEY"]
    ):
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
    if (
        request.headers.get("Authorization", None) is None
        or request.headers.get("Authorization").split(" ")[1]
        != environ["QUART_SUPABASE_SERVICE_ROLE_KEY"]
    ):
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
        "10.64000",
        "10.64395",
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
        response = (
            supabase_client.table("posts")
            .select(
                "id, guid, doi, url, archive_url, title, summary, abstract, content_html, published_at, updated_at, registered_at, indexed_at, authors, image, tags, language, reference, relationships, funding_references, blog_name, blog_slug, rid, blog: blogs!inner(*)",
                count="exact",
            )
            .not_.is_("blogs.prefix", "null")
            .is_("doi", "null")
            .is_("rid", "null")
            .in_("status", status)
            .order("published_at", desc=True)
            .limit(min(per_page, 50))
            .execute()
        )
        return jsonify({"total-results": response.count, "items": response.data})
    elif slug == "updated":
        response = (
            supabase_client.table("posts")
            .select(
                "id, guid, doi, url, archive_url, title, summary, abstract, content_html, published_at, updated_at, registered_at, indexed_at, authors, image, tags, language, reference, relationships, funding_references, blog_name, blog_slug, rid, blog: blogs!inner(*)",
                count="exact",
            )
            .not_.is_("blogs.prefix", "null")
            .is_("updated", True)
            .not_.is_("doi", "null")
            .in_("status", status)
            .order("updated_at", desc=True)
            .limit(min(per_page, 50))
            .execute()
        )
        return jsonify({"total-results": response.count, "items": response.data})
    elif slug == "waiting":
        response = (
            supabase_client.table("posts")
            .select(
                "id, guid, doi, url, archive_url, title, summary, abstract, content_html, published_at, updated_at, registered_at, indexed_at, authors, image, tags, language, reference, relationships, funding_references, blog_name, blog_slug, rid, blog: blogs!inner(*)",
                count="exact",
            )
            .not_.is_("blogs.prefix", "null")
            .lte("indexed_at", 1)
            .in_("status", status)
            .order("published_at", desc=True)
            .limit(min(per_page, 50))
            .execute()
        )
        return jsonify({"total-results": response.count, "items": response.data})
    elif slug == "cited":
        response = (
            supabase_client.table("posts")
            .select("*, citation: citations!inner(citation)", count="exact", head=True)
            .not_.is_("doi", "null")
            .execute()
        )
        total = response.count
        total_pages = ceil(total / 50)
        page = min(page, total_pages)
        start_page = (page - 1) * 50 if page > 0 else 0
        end_page = (page - 1) * 50 + 50 if page > 0 else 50

        response = (
            supabase_client.table("posts")
            .select(postsWithCitationsSelect, count="exact")
            .not_.is_("blogs.prefix", "null")
            .not_.is_("doi", "null")
            .order("updated_at", desc=True)
            .limit(min(per_page, 100))
            .range(start_page, end_page)
            .execute()
        )
        return jsonify({"total-results": response.count, "items": response.data})
    elif slug in prefixes and suffix and relation:
        if validate_uuid(slug):
            response = (
                supabase_client.table("posts")
                .select("reference")
                .eq("id", slug)
                .maybe_single()
                .execute()
            )
        else:
            doi = f"https://doi.org/{slug}/{suffix.lower()}"
            response = (
                supabase_client.table("posts")
                .select("reference")
                .eq("doi", doi)
                .maybe_single()
                .execute()
            )
        references = response.data.get("reference", [])
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
            response = (
                supabase_client.table("posts")
                .select(postsWithCitationsSelect)
                .eq("id", slug)
                .maybe_single()
                .execute()
            )
            if not response:
                response = (
                    supabase_client.table("posts")
                    .select(postsWithContentSelect)
                    .eq("id", slug)
                    .maybe_single()
                    .execute()
                )
            basename = slug
        else:
            doi = f"https://doi.org/{slug}/{suffix}"
            response = (
                supabase_client.table("posts")
                .select(postsWithCitationsSelect)
                .eq("doi", doi)
                .maybe_single()
                .execute()
            )
            if not response:
                response = (
                    supabase_client.table("posts")
                    .select(postsWithContentSelect)
                    .eq("doi", doi)
                    .maybe_single()
                    .execute()
                )
            basename = doi_from_url(doi).replace("/", "-")
        content = response.data.get("content_html", None)
        if format_ == "json":
            return jsonify(response.data)
        metadata = py_.omit(response.data, ["content_html"])
        meta = convert_to_commonmeta(metadata)
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
            markdown = frontmatter.dumps(markdown)
            pdf, error = write_pdf(markdown)
            if error is not None:
                logger.error(error)
            return (
                pdf,
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
    if (
        request.headers.get("Authorization", None) is None
        or request.headers.get("Authorization").split(" ")[1]
        != environ["QUART_SUPABASE_SERVICE_ROLE_KEY"]
    ):
        return {"error": "Unauthorized."}, 401

    try:
        result = await delete_all_draft_records()
        return jsonify(result)
    except APIError as e:
        return {"error": e.message or "An error occured."}, 400


@app.route("/records/<slug>", methods=["DELETE"])
async def delete_record(slug: str):
    """Delete InvenioRDM draft record using the rid."""
    if (
        request.headers.get("Authorization", None) is None
        or request.headers.get("Authorization").split(" ")[1]
        != environ["QUART_SUPABASE_SERVICE_ROLE_KEY"]
    ):
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
