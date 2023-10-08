import os
import logging
from typing import Optional
from dataclasses import dataclass
from datetime import datetime
from dotenv import load_dotenv
from quart import Quart, request, jsonify, redirect
from quart_schema import QuartSchema, Info, validate_request, validate_response
from supabase import create_client, Client as SupabaseClient
import typesense as ts


from rogue_scholar_api.utils import get_doi_metadata_from_ra, validate_uuid


app = Quart(__name__)
QuartSchema(app, info=Info(title="Rogue Scholar API", version="0.6.0"))


@dataclass
class Query:
    query: str
    tags: str
    language: str
    page: int


@dataclass
class Blog:
    slug: str
    title: str
    description: str
    language: str
    favicon: str
    feed_url: str
    feed_format: str
    home_page_url: str
    generator: str
    category: str
    backlog: int
    prefix: str
    status: str
    plan: str
    funding: str
    items: list


@dataclass
class Post:
    id: str
    doi: str
    url: str
    archive_url: str
    title: str
    summary: str
    content_html: str
    published_at: datetime
    updated_at: datetime
    indexed_at: datetime
    authors: list
    image: str
    tags: list
    language: str
    reference: str
    relationships: dict
    blog_name: str
    blog_slug: str
    blog: dict


load_dotenv()
supabase_url: str = os.environ.get("SUPABASE_URL")
supabase_key: str = os.environ.get("SUPABASE_ANON_KEY")
typesense_host: str = os.environ.get("TYPESENSE_HOST")
typesense_api_key: str = os.environ.get("TYPESENSE_API_KEY")

supabase: SupabaseClient = create_client(
    supabase_url=supabase_url, supabase_key=supabase_key
)
logger = logging.getLogger(__name__)
blogsSelect = "slug, title, description, language, favicon, feed_url, feed_format, home_page_url, generator, category"
blogWithPostsSelect = "slug, title, description, language, favicon, feed_url, current_feed_url, archive_prefix, feed_format, home_page_url, use_mastodon, created_at, modified_at, license, generator, category, backlog, prefix, status, plan, funding, items: posts (id, doi, url, archive_url, title, summary, published_at, updated_at, indexed_at, authors, image, tags, language, reference)"
postsSelect = "id, doi, url, archive_url, title, summary, published_at, updated_at, indexed_at, authors, image, tags, language, reference, relationships, blog_name, blog_slug"
postsWithConfigSelect = "id, doi, url, archive_url, title, summary, published_at, updated_at, indexed_at, indexed, authors, image, tags, language, reference, relationships, blog_name, blog_slug, blog: blogs!inner(slug, title, description, feed_url, home_page_url, language, category, status, generator, license, modified_at)"
postsWithBlogSelect = "id, doi, url, archive_url, title, summary, published_at, updated_at, indexed_at, indexed, authors, image, tags, language, reference, relationships, blog_name, blog_slug, blog: blogs!inner(*)"
postsWithContentSelect = "id, doi, url, archive_url, title, summary, content_html, published_at, updated_at, indexed_at, authors, image, tags, language, reference, relationships, blog_name, blog_slug, blog: blogs!inner(*)"
typesense = ts.Client(
    {
        "api_key": typesense_api_key,
        "nodes": [
            {
                "host": typesense_host,
                "port": "443",
                "protocol": "https",
            }
        ],
    }
)


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


@validate_request(Query)
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
