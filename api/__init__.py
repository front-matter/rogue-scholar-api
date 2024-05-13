"""Main quart application"""

from hypercorn.config import Config
import logging
from typing import Optional
from datetime import timedelta
import time
from os import environ
import pydash as py_
from dotenv import load_dotenv
import sentry_sdk
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
from quart_rate_limiter import RateLimiter, RateLimit
from quart_cors import cors
from postgrest import APIError

from api.supabase import (
    supabase_client as supabase,
    blogWithPostsSelect,
    postsWithContentSelect,
    worksSelect,
)
from api.typesense import typesense_client as typesense
from commonmeta import Metadata, doi_from_url, validate_prefix
from api.utils import (
    get_formatted_metadata,
    convert_to_commonmeta,
    write_epub,
    write_pdf,
    write_jats,
    format_markdown,
    validate_uuid,
    unix_timestamp,
    end_of_date,
    compact,
    format_datetime,
    format_authors,
    format_authors_full,
    format_authors_with_orcid,
    format_license,
    format_relationships,
    translate_titles,
)
from api.posts import extract_all_posts, extract_all_posts_by_blog, update_all_posts, update_all_posts_by_blog, update_single_post
from api.blogs import extract_single_blog, extract_all_blogs
from api.works import SUPPORTED_ACCEPT_HEADERS, get_formatted_work
from api.schema import Blog, Post, Work, PostQuery

config = Config()
config.from_toml("hypercorn.toml")
load_dotenv()
rate_limiter = RateLimiter()
logger = logging.getLogger(__name__)
version = "0.8.0"  # TODO: importlib.metadata.version('rogue-scholar-api')

sentry_sdk.init(
    dsn=environ["QUART_SENTRY_DSN"],
)
app = Quart(__name__)
app.config.from_prefixed_env()
QuartSchema(app, info=Info(title="Rogue Scholar API", version=version))
rate_limiter = RateLimiter(app, default_limits=[RateLimit(15, timedelta(seconds=60))])
app = cors(app, allow_origin="*")


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


@app.route("/works/")
@hide
async def works_redirect():
    """Redirect /works/ to /works."""
    return redirect("/works", code=301)


@validate_response(Work)
@app.route("/works")
async def works():
    """Show works."""
    per_page = int(request.args.get("per_page") or "10")
    page = int(request.args.get("page") or "1")
    start_page = (page - 1) * per_page if page > 0 else 0
    end_page = (page - 1) * per_page + (per_page - 1) if page > 0 else (per_page - 1)
    try:
        response = (
            supabase.table("works")
            .select(worksSelect, count="exact")
            .limit(min(per_page, 100))
            .order("date->published", desc=True)
            .range(start_page, end_page)
            .execute()
        )
        return jsonify({"total-results": response.count, "items": response.data})
    except APIError as e:
        return {"error": e.message or "An error occured."}, 400


@validate_response(Work)
@app.route("/works/<slug>")
@app.route("/works/<slug>/<suffix>")
async def work(slug: str, suffix: Optional[str] = None):
    """Get work by slug."""
    locale = request.args.get("locale") or "en-US"
    style = request.args.get("style") or "apa"

    try:
        if validate_uuid(slug):
            response = (
                supabase.table("works")
                .select(worksSelect)
                .eq("uuid", slug)
                .maybe_single()
                .execute()
            )
            return jsonify(response.data)
        elif validate_prefix(slug) and suffix:
            doi = f"https://doi.org/{slug}/{suffix}"
            response = (
                supabase.table("works")
                .select(worksSelect)
                .eq("id", doi)
                .maybe_single()
                .execute()
            )
        else:
            logger.warning(f"Invalid slug: {slug}")
            return {"error": "An error occured."}, 400
    except APIError as e:
        if e.code == "204":
            return {"error": "Work not found."}, 404
        return {"error": e.message or "An error occured."}, 400

    accept_header = request.accept_mimetypes.best

    if accept_header not in SUPPORTED_ACCEPT_HEADERS:
        return jsonify(response.data)
    subject = Metadata(response.data, via="commonmeta")
    result = get_formatted_work(subject, accept_header, style, locale)
    return result.strip(), 200, {"Content-Type": accept_header}


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
    preview = request.args.get("preview")
    query = request.args.get("query") or ""
    query_by = (
        request.args.get("query_by")
        or "slug,title,description,category,language,generator,prefix,funding"
    )
    category = request.args.get("category")
    generator = request.args.get("generator")
    language = request.args.get("language")
    page = int(request.args.get("page") or "1")
    per_page = int(request.args.get("per_page") or "10")
    # default sort depends on whether a query is provided
    _text_match = "_text_match" if request.args.get("query") else "updated_at"
    sort = (
        f"{request.args.get('sort')}(missing_values: last)"
        if request.args.get("sort")
        else _text_match
    )
    order = request.args.get("order") or "desc"
    include_fields = request.args.get("include_fields")

    # filter blogs by status, category, generator, and/or language
    filter_by = "status:!=[submitted]" if preview else "status:!=[submitted,pending]"
    filter_by = f"category:>= {category}" if category else filter_by
    filter_by = filter_by + f" && generator:=[{generator}]" if generator else filter_by
    filter_by = filter_by + f" && language:=[{language}]" if language else filter_by
    search_parameters = compact(
        {
            "q": query,
            "query_by": query_by,
            "filter_by": filter_by,
            "sort_by": f"{sort}:{order}",
            "per_page": min(per_page, 50),
            "page": page if page and page > 0 else 1,
            "include_fields": include_fields,
        }
    )
    try:
        response = typesense.collections["blogs"].documents.search(search_parameters)
        return jsonify(py_.omit(response, ["hits.highlight"]))
    except Exception as e:
        logger.warning(e.args[0])
        return {"error": "An error occured."}, 400


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
        supabase.table("blogs")
        .select(blogWithPostsSelect)
        .eq("slug", slug)
        .maybe_single()
        .execute()
    )
    return jsonify(response.data)


@validate_response(Blog)
@app.route("/blogs/<slug>", methods=["POST"])
async def post_blog(slug):
    """Update blog by slug, using information from the blog's feed."""
    result = await extract_single_blog(slug)
    return jsonify(result)


@validate_response(Blog)
@app.route("/blogs/<slug>/<suffix>", methods=["POST"])
async def post_blog_posts(slug: str, suffix: Optional[str] = None):
    """Update blog posts by slug."""

    page = int(request.args.get("page") or "1")
    offset = request.args.get("offset")
    if offset is not None:
        offset = int(offset)
    update = request.args.get("update")

    if (
        request.headers.get("Authorization", None) is None
        or request.headers.get("Authorization").split(" ")[1]
        != environ["QUART_SUPABASE_SERVICE_ROLE_KEY"]
    ):
        return {"error": "Unauthorized."}, 401
    elif slug and suffix == "posts":
        try:
            if update == "self":
                result = await update_all_posts_by_blog(slug, page=page)
            else:
                result = await extract_all_posts_by_blog(
                    slug, page=page, offset=offset, update_all=(update == "all")
                )
            if isinstance(result, dict) and result.get("error", None):
                return result, 400
            return jsonify(result)
        except Exception as e:
            logger.warning(e.args[0])
            return {"error": "An error occured."}, 400
    else:
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
    """Search posts by query, tags, language, category. Options to change page, per_page and include fields."""
    preview = request.args.get("preview")
    query = request.args.get("query") or ""
    query_by = (
        request.args.get("query_by")
        or "tags,title,doi,authors.name,authors.url,summary,abstract,content_text,reference"
    )
    tags = request.args.get("tags")
    language = request.args.get("language")
    category = request.args.get("category")
    page = int(request.args.get("page") or "1")
    per_page = int(request.args.get("per_page") or "10")
    # default sort depends on whether a query is provided
    _text_match = "_text_match" if request.args.get("query") else "published_at"
    sort = (
        f"{request.args.get('sort')}(missing_values: last)"
        if request.args.get("sort")
        else _text_match
    )
    order = request.args.get("order") or "desc"
    include_fields = request.args.get("include_fields")
    blog_slug = request.args.get("blog_slug")
    published_since = (
        unix_timestamp(request.args.get("published_since"))
        if request.args.get("published_since")
        else 0
    )
    published_until = (
        unix_timestamp(end_of_date(request.args.get("published_until")))
        if request.args.get("published_until")
        else int(time.time())
    )
    # filter posts by status, date published, blog, tags, and/or language
    filter_by = "status:=[pending,active]" if preview else "status:!=[pending]"
    filter_by = filter_by + (
        f" && published_at:>= {published_since} && published_at:<= {published_until}"
    )
    filter_by = filter_by + f" && blog_slug:{blog_slug}" if blog_slug else filter_by
    filter_by = filter_by + f" && tags:=[{tags}]" if tags else filter_by
    filter_by = filter_by + f" && language:=[{language}]" if language else filter_by
    filter_by = filter_by + f" && category:>= {category}" if category else filter_by
    search_parameters = compact(
        {
            "q": query,
            "query_by": query_by,
            "filter_by": filter_by,
            "sort_by": f"{sort}:{order}",
            "per_page": min(per_page, 50),
            "page": page if page and page > 0 else 1,
            "include_fields": include_fields,
        }
    )
    try:
        response = typesense.collections["posts"].documents.search(search_parameters)
        return jsonify(py_.omit(response, ["hits.highlight"]))
    except Exception as e:
        logger.warning(e.args[0])
        return {"error": "An error occured."}, 400


@app.route("/posts", methods=["POST"])
async def post_posts():
    """Update posts."""

    page = int(request.args.get("page") or "1")
    update = request.args.get("update")

    if (
        request.headers.get("Authorization", None) is None
        or request.headers.get("Authorization").split(" ")[1]
        != environ["QUART_SUPABASE_SERVICE_ROLE_KEY"]
    ):
        return {"error": "Unauthorized."}, 401
    else:
        try:
            if update == "self":
                updated_posts = await update_all_posts(page=page)
                return jsonify(updated_posts)
            else:
                extracted_posts = await extract_all_posts(
                    page=page, update_all=(update == "all")
                )
            return jsonify(extracted_posts)
        except Exception as e:
            logger.warning(e)
            return {"error": "An error occured."}, 400

@validate_response(Post)
@app.route("/posts/<slug>", methods=["POST"])
@app.route("/posts/<slug>/<suffix>", methods=["POST"])
async def post_post(slug: str, suffix: Optional[str] = None):
    """Update post by either uuid or doi, using information from the blog's feed."""
    
    try:
        result = await update_single_post(slug, suffix=suffix)
        return jsonify(result)
    except Exception as e:
        logger.warning(e.args[0])
        return {"error": "An error occured."}, 400


@validate_response(Post)
@app.route("/posts/<slug>")
@app.route("/posts/<slug>/<suffix>")
@app.route("/posts/<slug>/<suffix>/<relation>")
async def post(slug: str, suffix: Optional[str] = None, relation: Optional[str] = None):
    """Get post by slug."""
    prefixes = [
        "10.13003",
        "10.34732",
        "10.53731",
        "10.54900",
        "10.57689",
        "10.59348",
        "10.59349",
        "10.59350",
        "10.59704",
    ]
    permitted_slugs = ["unregistered", "updated"] + prefixes
    if slug not in permitted_slugs and not validate_uuid(slug):
        logger.warning(f"Invalid slug: {slug}")
        return {"error": "An error occured."}, 400
    format_ = request.args.get("format") or "json"
    locale = request.args.get("locale") or "en-US"
    style = request.args.get("style") or "apa"
    per_page = int(request.args.get("per_page") or "50")
    if slug == "unregistered":
        response = (
            supabase.table("posts")
            .select(postsWithContentSelect, count="exact")
            .not_.is_("blogs.prefix", "null")
            .is_("doi", "null")
            .order("published_at", desc=True)
            .limit(min(per_page, 100))
            .execute()
        )
        return jsonify({"total-results": response.count, "items": response.data})
    elif slug == "updated":
        response = (
            supabase.table("posts")
            .select(postsWithContentSelect, count="exact")
            .not_.is_("blogs.prefix", "null")
            .is_("updated", True)
            .not_.is_("doi", "null")
            .order("updated_at", desc=True)
            .limit(min(per_page, 100))
            .execute()
        )
        return jsonify({"total-results": response.count, "items": response.data})
    elif slug in prefixes and suffix and relation:
        if validate_uuid(slug):
            response = (
                supabase.table("posts")
                .select("reference")
                .eq("id", slug)
                .maybe_single()
                .execute()
            )
        else:
            doi = f"https://doi.org/{slug}/{suffix}"
            response = (
                supabase.table("posts")
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
                supabase.table("posts")
                .select(postsWithContentSelect)
                .eq("id", slug)
                .maybe_single()
                .execute()
            )
            basename = slug
        else:
            doi = f"https://doi.org/{slug}/{suffix}"
            response = (
                supabase.table("posts")
                .select(postsWithContentSelect)
                .eq("doi", doi)
                .maybe_single()
                .execute()
            )
            basename = doi_from_url(doi).replace("/", "-")
        content = response.data.get("content_text", None)
        if format_ == "json":
            return jsonify(response.data)
        metadata = py_.omit(response.data, ["content_text"])
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
        markdown = format_markdown(content, metadata)
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


@app.errorhandler(RequestSchemaValidationError)
async def handle_request_validation_error():
    return {"error": "VALIDATION"}, 400
