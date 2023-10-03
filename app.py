import os
from dotenv import load_dotenv
from supabase import create_client, Client
from quart import Quart

app = Quart(__name__)
load_dotenv()
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_ANON_KEY")
supabase: Client = create_client(supabase_url=url, supabase_key=key)
blogsSelect = "slug, title, description, language, favicon, feed_url, feed_format, home_page_url, generator, category"


@app.route("/")
def default():
    return "Hello World"


@app.route("/blogs")
async def blogs():
    response = (
        supabase.table("blogs")
        .select(blogsSelect)
        .eq("status", "active")
        .order("title")
        .execute()
    )
    return response.data


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)
