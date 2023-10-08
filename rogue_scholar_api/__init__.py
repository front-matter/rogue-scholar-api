import os
import logging
from uuid import UUID
from dotenv import load_dotenv
from supabase import create_client, Client as SupabaseClient
from quart import Quart, request, jsonify, redirect
import typesense as ts


from rogue_scholar_api.utils import get_doi_metadata_from_ra


app = Quart(__name__)

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
    return redirect('/blogs', code=301)


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
    return redirect('/posts', code=301)


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


@app.route("/posts/<slug>")
@app.route("/posts/<slug>/<suffix>")
async def post(slug, suffix=None):
    prefixes = [
        "10.34732",
        "10.53731",
        "10.54900",
        "10.57689",
        "10.59348",
        "10.59349",
        "10.59350",
    ]
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
            content_types = {
                "bibtex": "application/x-bibtex",
                "ris": "application/x-research-info-systems",
                "csl": "application/vnd.citationstyles.csl+json",
                "citation": f"text/x-bibliography; style={style}; locale={locale}",
            }
            content_type = content_types.get(format_)
            metadata = get_doi_metadata_from_ra(doi, headers={"Accept": content_type})
            if not metadata:
                logger.warning(f"Metadata not found for {doi}")
                return {"error": "Metadata not found."}, 404
            if format_ == "csl":
                filename = f"{slug}-{suffix}.json"
            elif format_ == "ris":
                filename = f"{slug}-{suffix}.ris"
            elif format_ == "bibtex":
                filename = f"{slug}-{suffix}.bib"
            else:
                filename = f"{slug}-{suffix}.txt"
            options = {
                "Content-Type": content_type,
                "Content-Disposition": f"attachment; filename={filename}",
            }
            return (metadata, 200, options)
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
        # Check if slug is a valid UUID
        try:
            UUID(slug, version=4)
        except ValueError as e:
            logger.warning(e.args[0])
            return {"error": e.args[0]}, 400
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
