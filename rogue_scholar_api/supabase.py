"""Supabase client configuration"""
from os import environ
from dotenv import load_dotenv
from supabase import create_client, Client as SupabaseClient

load_dotenv()

supabase_client: SupabaseClient = create_client(
    supabase_url=environ["QUART_SUPABASE_URL"],
    supabase_key=environ["QUART_SUPABASE_ANON_KEY"],
)

supabase_admin_client: SupabaseClient = create_client(
    supabase_url=environ["QUART_SUPABASE_URL"],
    supabase_key=environ["QUART_SUPABASE_SERVICE_ROLE_KEY"],
)

blogsSelect = "slug, title, description, language, favicon, feed_url, feed_format, home_page_url, generator, category"
blogWithPostsSelect = "slug, title, description, language, favicon, feed_url, current_feed_url, archive_prefix, feed_format, home_page_url, use_mastodon, created_at, modified_at, license, generator, category, backlog, prefix, status, plan, funding, items: posts (id, doi, url, archive_url, title, summary, published_at, updated_at, indexed_at, authors, image, tags, language, reference)"
postsSelect = "id, doi, url, archive_url, title, summary, published_at, updated_at, indexed_at, authors, image, tags, language, reference, relationships, blog_name, blog_slug"
postsWithConfigSelect = "id, doi, url, archive_url, title, summary, published_at, updated_at, indexed_at, indexed, authors, image, tags, language, reference, relationships, blog_name, blog_slug, blog: blogs!inner(slug, title, description, feed_url, home_page_url, language, category, status, generator, license, updated_at, modified_at)"
postsWithBlogSelect = "id, doi, url, archive_url, title, summary, published_at, updated_at, indexed_at, indexed, authors, image, tags, language, reference, relationships, blog_name, blog_slug, blog: blogs!inner(*)"
postsWithContentSelect = "id, doi, url, archive_url, title, summary, content_html, published_at, updated_at, indexed_at, authors, image, tags, language, reference, relationships, blog_name, blog_slug, blog: blogs!inner(*)"
