import os
from dotenv import load_dotenv
from supabase import create_client, Client
from quart import Quart, request


app = Quart(__name__)
load_dotenv()
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_ANON_KEY")
supabase: Client = create_client(supabase_url=url, supabase_key=key)
blogsSelect = "slug, title, description, language, favicon, feed_url, feed_format, home_page_url, generator, category"
blogWithPostsSelect = "slug, title, description, language, favicon, feed_url, current_feed_url, archive_prefix, feed_format, home_page_url, use_mastodon, created_at, modified_at, license, generator, category, backlog, prefix, status, plan, funding, items: posts (id, doi, url, archive_url, title, summary, published_at, updated_at, indexed_at, authors, image, tags, language, reference)"


@app.route("/")
def default():
    return "This is the Rogue Scholar API."


@app.route("/blogs")
async def blogs():
    page = int(request.args.get('page') or "1")
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
async def page(slug):
    response = (
        supabase.table("blogs")
        .select(blogWithPostsSelect)
        .eq("slug", slug)
        .maybe_single()
        .execute()
    )
    return response.data


if __name__ == "__main__":
    app.run()
