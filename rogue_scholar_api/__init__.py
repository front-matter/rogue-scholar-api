import logging
from typing import Optional
from quart import Quart, request, jsonify, redirect
from quart_schema import QuartSchema, Info, validate_request, validate_response

from rogue_scholar_api.supabase import (
    supabase_client as supabase,
    blogsSelect,
    blogWithPostsSelect,
    postsWithConfigSelect,
    postsWithContentSelect,
)
from rogue_scholar_api.typesense import typesense_client as typesense
from rogue_scholar_api.utils import get_doi_metadata_from_ra, validate_uuid
from rogue_scholar_api.schema import Blog, Post, PostQuery

app = Quart(__name__)
QuartSchema(app, info=Info(title="Rogue Scholar API", version="0.6.0"))

logger = logging.getLogger(__name__)


def run() -> None:
    app.run()


@app.route("/")
def default():
    return redirect("https://rogue-scholar.org", code=301)


@app.route("/blogs/")
async def blogs_redirect():
    return redirect("/blogs", code=301)


@validate_response(Blog)
@app.route("/blogs")
async def blogs():
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
    response = (
        supabase.table("blogs")
        .select(blogWithPostsSelect)
        .eq("slug", slug)
        .maybe_single()
        .execute()
    )
    return jsonify(response.data)


@app.route("/posts/")
async def posts_redirect():
    return redirect("/posts", code=301)


@validate_request(PostQuery)
@validate_response(Post)
@app.route("/posts")
async def posts():
    query = request.args.get("query") or ""
    tags = request.args.get("tags")
    language = request.args.get("language")
    page = int(request.args.get("page") or "1")
    filter_by = "blog_slug:!=[xxx]"
    filter_by = filter_by + f" && tags:=[{tags}]" if tags else filter_by
    filter_by = filter_by + f" && language:=[{language}]" if language else filter_by
    search_parameters = {
        "q": query,
        "query_by": "tags,title,doi,authors.name,authors.url,summary,content_html,reference",
        "filter_by": filter_by,
        "sort_by": "_text_match:desc"
        if request.args.get("query")
        else "published_at:desc",
        "per_page": 10,
        "page": page if page and page > 0 else 1,
    }
    try:
        response = typesense.collections["posts"].documents.search(search_parameters)
        return jsonify(response)
    except Exception as e:
        logger.warning(e.args[0])
        return {"error": "An error occured."}, 400


@validate_response(Post)
@app.route("/posts/<slug>")
@app.route("/posts/<slug>/<suffix>")
async def post(slug: str, suffix: Optional[str] = None):
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
