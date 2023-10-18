"""Main quart application"""
import logging
from typing import Optional
from datetime import timedelta
from commonmeta.utils import compact
from os import environ
from dotenv import load_dotenv
import sentry_sdk

# import importlib.metadata
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

from rogue_scholar_api.supabase import (
    supabase_client as supabase,
    # supabase_admin_client as supabase_admin,
    blogsSelect,
    blogWithPostsSelect,
    postsWithConfigSelect,
    postsWithContentSelect,
)
from rogue_scholar_api.typesense import typesense_client as typesense
from rogue_scholar_api.utils import (
    get_doi_metadata_from_ra,
    validate_uuid,
    unix_timestamp,
)
from rogue_scholar_api.schema import Blog, Post, PostQuery

load_dotenv()
rate_limiter = RateLimiter()
logger = logging.getLogger(__name__)
version = "0.6.2"  # TODO: importlib.metadata.version('rogue-scholar-api')

sentry_sdk.init(
    dsn=environ["QUART_SENTRY_DSN"],
    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for performance monitoring.
    traces_sample_rate=1.0,
)
app = Quart(__name__)
app.config.from_prefixed_env()
QuartSchema(app, info=Info(title="Rogue Scholar API", version=version))
rate_limiter = RateLimiter(app, default_limits=[RateLimit(15, timedelta(seconds=60))])


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


@validate_response(Blog)
@app.route("/blogs")
async def blogs():
    """Get all blogs."""
    page = int(request.args.get("page") or "1")
    start_page = (page - 1) * 100 if page > 0 else 0
    end_page = start_page + 100
    response = (
        supabase.table("blogs")
        .select(blogsSelect)
        .in_("status", ["approved", "active", "archived"])
        .order("title", desc=False)
        .range(start_page, end_page)
        .execute()
    )
    return jsonify(response.data)


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
@app.route("/blogs/<slug>/<suffix>", methods=["POST"])
async def post_blog(slug: str, suffix: Optional[str] = None):
    """Update blog by slug."""
    if suffix is None:
        response = (
            supabase.table("blogs")
            .select(blogWithPostsSelect)
            .eq("slug", slug)
            .maybe_single()
            .execute()
        )
        return jsonify(response.data)
    elif slug and suffix == "posts":
        response = (
            supabase.table("posts")
            .select(postsWithConfigSelect)
            .eq("blog_slug", slug)
            .order("published_at", desc=True)
            .limit(10)
            .execute()
        )
        return jsonify(response.data)


@app.route("/posts/")
@hide
async def posts_redirect():
    """Redirect /posts/ to /posts."""
    return redirect("/posts", code=301)


@validate_request(PostQuery)
@validate_response(Post)
@app.route("/posts")
async def posts():
    """Search posts by query, tags, language. Options to change page, per_page and include fields."""
    query = request.args.get("query") or ""
    tags = request.args.get("tags")
    language = request.args.get("language")
    page = int(request.args.get("page") or "1")
    per_page = int(request.args.get("per_page") or "10")
    # default sort depends on whether a query is provided
    _text_match = request.args.get("query") and "_text_match" or "published_at"
    sort = request.args.get("sort") or _text_match
    order = request.args.get("order") == "asc" and "asc" or "desc"
    include_fields = request.args.get("include_fields")
    blog_slug = request.args.get("blog_slug")
    published_since = (
        unix_timestamp(request.args.get("published_since"))
        if request.args.get("published_since")
        else 0
    )
    # filter posts by date published, blog, tags, and/or language
    filter_by = f"published_at:>= {published_since}"
    filter_by = f"blog_slug:{blog_slug}" if blog_slug else filter_by
    filter_by = filter_by + f" && tags:=[{tags}]" if tags else filter_by
    filter_by = filter_by + f" && language:=[{language}]" if language else filter_by
    search_parameters = compact(
        {
            "q": query,
            "query_by": "tags,title,doi,authors.name,authors.url,summary,content_html,reference",
            "filter_by": filter_by,
            "sort_by": f"{sort}:{order}"
            if request.args.get("query")
            else "published_at:desc",
            "per_page": min(per_page, 50),
            "page": page if page and page > 0 else 1,
            "include_fields": include_fields,
        }
    )
    try:
        response = typesense.collections["posts"].documents.search(search_parameters)
        return jsonify(response)
    except Exception as e:
        logger.warning(e.args[0])
        return {"error": "An error occured."}, 400


@validate_response(Post)
@app.route("/posts", methods=["POST"])
async def post_posts():
    """Update posts."""
    if (
        request.headers.get("Authorization", None) is None
        or request.headers.get("Authorization").split(" ")[1]
        != environ["QUART_SUPABASE_SERVICE_ROLE_KEY"]
    ):
        return {"error": "Unauthorized."}, 401

    response = (
        supabase.table("blogs")
        .select("slug")
        .eq("status", "active")
        .order("slug", desc=False)
        .execute()
    )
    return jsonify(response.data)
    return {"error": "An error occured."}, 400


@validate_response(Post)
@app.route("/posts/<slug>")
@app.route("/posts/<slug>/<suffix>")
async def post(slug: str, suffix: Optional[str] = None):
    """Get post by slug."""
    prefixes = [
        "10.34732",
        "10.53731",
        "10.54900",
        "10.57689",
        "10.59348",
        "10.59349",
        "10.59350",
    ]
    permitted_slugs = ["unregistered", "not_indexed"] + prefixes
    if slug not in permitted_slugs and not validate_uuid(slug):
        logger.warning(f"Invalid slug: {slug}")
        return {"error": "An error occured."}, 400
    format_ = request.args.get("format") or "json"
    locale = request.args.get("locale") or "en-US"
    style = request.args.get("style") or "apa"
    formats = ["bibtex", "ris", "csl", "citation"]
    if slug == "unregistered":
        response = (
            supabase.table("posts")
            .select(postsWithConfigSelect)
            .not_.is_("blogs.prefix", "null")
            .is_("doi", "null")
            .order("published_at", desc=True)
            .limit(15)
            .execute()
        )
        return jsonify(response.data)
    elif slug == "not_indexed":
        response = (
            supabase.table("posts")
            .select(postsWithConfigSelect)
            .not_.is_("blogs.prefix", "null")
            .is_("indexed", "null")
            .not_.is_("doi", "null")
            .order("published_at", desc=True)
            .limit(15)
            .execute()
        )
        return jsonify(response.data)
    elif slug in prefixes and suffix:
        doi = f"https://doi.org/{slug}/{suffix}"
        if format_ in formats:
            response = get_doi_metadata_from_ra(doi, format_, style, locale)
            if not response:
                logger.warning("Metadata not found")
                return {"error": "Metadata not found."}, 404
            return (response["data"], 200, response["options"])
        else:
            try:
                response = (
                    supabase.table("posts")
                    .select(postsWithContentSelect)
                    .eq("doi", doi)
                    .maybe_single()
                    .execute()
                )
            except Exception as e:
                logger.warning(e.args[0])
                return {"error": "Post not found"}, 404
            return jsonify(response.data)
    else:
        try:
            response = (
                supabase.table("posts")
                .select(postsWithContentSelect)
                .eq("id", slug)
                .maybe_single()
                .execute()
            )
        except Exception as e:
            logger.warning(e.args[0])
            return {"error": "Post not found"}, 404
        return jsonify(response.data)


@app.errorhandler(RequestSchemaValidationError)
async def handle_request_validation_error():
    return {"error": "VALIDATION"}, 400
