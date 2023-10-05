import os
from dotenv import load_dotenv
from supabase import create_client, Client as SupabaseClient
from quart import Quart, request
import typesense as ts
from typesense.exceptions import TypesenseClientError


app = Quart(__name__)
load_dotenv()
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_ANON_KEY")
supabase: SupabaseClient = create_client(supabase_url=url, supabase_key=key)
blogsSelect = "slug, title, description, language, favicon, feed_url, feed_format, home_page_url, generator, category"
blogWithPostsSelect = "slug, title, description, language, favicon, feed_url, current_feed_url, archive_prefix, feed_format, home_page_url, use_mastodon, created_at, modified_at, license, generator, category, backlog, prefix, status, plan, funding, items: posts (id, doi, url, archive_url, title, summary, published_at, updated_at, indexed_at, authors, image, tags, language, reference)"
postsSelect = "id, doi, url, archive_url, title, summary, published_at, updated_at, indexed_at, authors, image, tags, language, reference, relationships, blog_name, blog_slug"
typesense = ts.Client(
    {
        "api_key": os.environ.get("TYPESENSE_API_KEY"),
        "nodes": [
            {
                "host": os.environ.get("TYPESENSE_HOST"),
                "port": "443",
                "protocol": "https",
            }
        ],
    }
)


@app.route("/")
def default():
    return "This is the Rogue Scholar API."


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
    return response.data


@app.route("/blogs/<slug>")
async def blog(slug):
    response = (
        supabase.table("blogs")
        .select(blogWithPostsSelect)
        .eq("slug", slug)
        .maybe_single()
        .execute()
    )
    return response.data


@app.route("/posts")
async def posts():
    slug = request.args.get("slug")
    query = request.args.get("query") or ""
    page = int(request.args.get("page") or "1")
    # format = request.args.get('format') or "json"
    # locale = request.args.get('locale') or "en-US"
    # style = request.args.get('locale') or "apa"
    # prefixes = [
    #     "10.34732",
    #     "10.53731",
    #     "10.54900",
    #     "10.57689",
    #     "10.59348",
    #     "10.59349",
    #     "10.59350",
    # ]
    # formats = ["bibtex", "ris", "csl", "citation"]
    search_parameters = {
        "q": query,
        "query_by": "tags,title,doi,authors.name,authors.url,summary,content_html,reference",
        "sort_by": "_text_match:desc"
        if request.args.get("query")
        else "published_at:desc",
        "per_page": 10,
        "page": page if page and page > 0 else 1,
    }
    response = typesense.collections["posts"].documents.search(search_parameters)
    return response


@app.route("/posts/<slug>")
async def post(slug):
    response = (
        supabase.table("posts")
        .select(postsSelect)
        .eq("id", slug)
        .maybe_single()
        .execute()
    )
    return response.data


if __name__ == "__main__":
    app.run()
