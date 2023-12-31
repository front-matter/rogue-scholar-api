"""Main quart application"""
from hypercorn.config import Config
import logging
from typing import Optional
from datetime import timedelta, datetime
import time
from os import environ
import pydash as py_
from dotenv import load_dotenv
import sentry_sdk
import frontmatter

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

from api.supabase import (
    supabase_client as supabase,
    blogWithPostsSelect,
    postsSelect,
    postsWithConfigSelect,
    postsWithContentSelect,
)
from api.typesense import typesense_client as typesense
from api.utils import (
    doi_from_url,
    get_doi_metadata_from_ra,
    write_epub,
    write_pdf,
    format_markdown,
    validate_uuid,
    unix_timestamp,
    end_of_date,
    compact,
    format_datetime,
    format_authors
)
from api.posts import extract_all_posts, extract_all_posts_by_blog, update_posts
from api.blogs import extract_single_blog, extract_all_blogs
from api.schema import Blog, Post, PostQuery

config = Config()
config.from_toml("hypercorn.toml")
load_dotenv()
rate_limiter = RateLimiter()
logger = logging.getLogger(__name__)
version = "0.7.1"  # TODO: importlib.metadata.version('rogue-scholar-api')

sentry_sdk.init(
    dsn=environ["QUART_SENTRY_DSN"],
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
    """Search blogs by query, category, generator, language.
    Options to change page, per_page and include fields."""
    query = request.args.get("query") or ""
    category = request.args.get("category")
    generator = request.args.get("generator")
    language = request.args.get("language")
    page = int(request.args.get("page") or "1")
    per_page = int(request.args.get("per_page") or "10")
    # default sort depends on whether a query is provided
    _text_match = "_text_match" if request.args.get("query") else "title"
    sort = request.args.get("sort") or _text_match
    order = request.args.get("order") or "asc"
    include_fields = request.args.get("include_fields")

    # filter blogs by category, generator, and/or language
    filter_by = "status:!=[submitted]"
    filter_by = f"category:>= {category}" if category else filter_by
    filter_by = filter_by + f" && generator:=[{generator}]" if generator else filter_by
    filter_by = filter_by + f" && language:=[{language}]" if language else filter_by
    search_parameters = compact(
        {
            "q": query,
            "query_by": "slug,title,description,category,language,generator,prefix,funding",
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
    update = request.args.get("update")

    if (
        request.headers.get("Authorization", None) is None
        or request.headers.get("Authorization").split(" ")[1]
        != environ["QUART_SUPABASE_SERVICE_ROLE_KEY"]
    ):
        return {"error": "Unauthorized."}, 401
    elif slug and suffix == "posts":
        try:
            result = await extract_all_posts_by_blog(
                slug, page=page, update_all=(update == "all")
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
    query = request.args.get("query") or ""
    tags = request.args.get("tags")
    language = request.args.get("language")
    category = request.args.get("category")
    page = int(request.args.get("page") or "1")
    per_page = int(request.args.get("per_page") or "10")
    # default sort depends on whether a query is provided
    _text_match = "_text_match" if request.args.get("query") else "published_at"
    sort = request.args.get("sort") or _text_match
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
    # filter posts by date published, blog, tags, and/or language
    filter_by = (
        f"published_at:>= {published_since} && published_at:<= {published_until}"
    )
    filter_by = filter_by + f" && blog_slug:{blog_slug}" if blog_slug else filter_by
    filter_by = filter_by + f" && tags:=[{tags}]" if tags else filter_by
    filter_by = filter_by + f" && language:=[{language}]" if language else filter_by
    filter_by = filter_by + f" && category:>= {category}" if category else filter_by
    search_parameters = compact(
        {
            "q": query,
            "query_by": "tags,title,doi,authors.name,authors.url,summary,content_text,reference",
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
    content_text = request.args.get("content_text")

    if (
        request.headers.get("Authorization", None) is None
        or request.headers.get("Authorization").split(" ")[1]
        != environ["QUART_SUPABASE_SERVICE_ROLE_KEY"]
    ):
        return {"error": "Unauthorized."}, 401
    else:
        try:
            if content_text == "content_text":
                response = typesense.collections["posts"].documents.search(
                    {
                        "q": "",
                        "query_by": "content_text",
                        "sort_by": "published_at:desc",
                        "per_page": 50,
                        "page": page if page and page > 0 else 1,
                        "filter_by": "content_text:content_text",
                        "include_fields": "id,doi,content_text",
                    }
                )
                updated_posts = await update_posts(response.get("hits", []))
                return jsonify(updated_posts)
            else:
                extracted_posts = await extract_all_posts(
                    page=page, update_all=(update == "all")
                )
            return jsonify(extracted_posts)
        except Exception as e:
            logger.warning(e)  # .args[0])
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
    permitted_slugs = ["unregistered", "updated"] + prefixes
    if slug not in permitted_slugs and not validate_uuid(slug):
        logger.warning(f"Invalid slug: {slug}")
        return {"error": "An error occured."}, 400
    format_ = request.args.get("format") or "json"
    locale = request.args.get("locale") or "en-US"
    style = request.args.get("style") or "apa"
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
    elif slug == "updated":
        response = (
            supabase.table("posts")
            .select(postsWithConfigSelect)
            .not_.is_("blogs.prefix", "null")
            .is_("updated", True)
            .not_.is_("doi", "null")
            .order("updated_at", desc=True)
            .limit(15)
            .execute()
        )
        return jsonify(response.data)
    elif slug in prefixes and suffix:
        path = suffix.split(".")
        if len(path) == 2 and path[1] in ["md", "epub", "pdf", "bib", "ris"]:
            suffix = path[0]
            format_ = path[1]
        if format_ == "bib":
            format_ = "bibtex"
        doi = f"https://doi.org/{slug}/{suffix}"
        if format_ in ["md", "epub", "pdf"]:
            try:
                response = (
                    supabase.table("posts")
                    .select(postsSelect)
                    .eq("doi", doi)
                    .maybe_single()
                    .execute()
                )
                basename = doi_from_url(doi).replace("/", "-")
    
                content = response.data.get("content_text", None)
                metadata = py_.omit(response.data, ["content_text"])
                metadata = py_.rename_keys(
                    metadata,
                    {
                        "authors": "author",
                        "blog_name": "publisher",
                        "doi": "identifier",
                        "language": "lang",
                        "published_at": "date",
                        "summary": "abstract",
                        "tags": "keywords",
                        "updated_at": "date_updated",
                    },
                )
                markdown = format_markdown(content, metadata)
                if format_ == "epub":
                    markdown["date"] = format_datetime(markdown["date"])
                    markdown["author"] = format_authors(markdown["author"])
                    markdown["rights"] = None
                    markdown = frontmatter.dumps(markdown)
                    epub = write_epub(markdown)
                    return (
                        epub,
                        200,
                        {"Content-Type": "application/epub+zip", "Content-Disposition": f"attachment; filename={basename}.epub",},
                    )
                elif format_ == "pdf":
                    markdown["date"] = format_datetime(markdown["date"])
                    markdown["abstract"] = None
                    markdown["author"] = format_authors(markdown["author"])
                    markdown = frontmatter.dumps(markdown)
                    pdf = write_pdf(markdown)
                    return (
                        pdf,
                        200,
                        {"Content-Type": "application/pdf", "Content-Disposition": f"attachment; filename={basename}.pdf",},
                    )
                else:
                    return (
                        frontmatter.dumps(markdown),
                        200,
                        {"Content-Type": "text/markdown;charset=UTF-8", "Content-Disposition": f"attachment; filename={basename}.md",},
                    )
            except Exception as e:
                logger.warning(e.args[0])
                return {"error": "Post not found"}, 404
        elif format_ in ["bibtex", "ris", "csl", "citation"]:
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
