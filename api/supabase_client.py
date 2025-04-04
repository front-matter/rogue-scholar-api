"""Supabase client configuration"""

from os import environ
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

supabase_client: Client = create_client(
    supabase_url=environ["QUART_SUPABASE_URL"],
    supabase_key=environ["QUART_SUPABASE_ANON_KEY"],
)

supabase_admin_client: Client = create_client(
    supabase_url=environ["QUART_SUPABASE_URL"],
    supabase_key=environ["QUART_SUPABASE_SERVICE_ROLE_KEY"],
)

blogsSelect = "slug, title, description, language, favicon, feed_url, feed_format, home_page_url, generator, category"
blogWithPostsSelect = "slug, title, description, language, favicon, feed_url, current_feed_url, archive_collection, archive_timestamps, feed_format, home_page_url, mastodon, created_at, license, generator, category, prefix, status, funding, items: posts (id, guid, doi, url, archive_url, title, summary, abstract, published_at, updated_at, registered_at, indexed_at, authors, image, tags, language, reference)"
postsSelect = "guid, doi, parent_doi, url, title, summary, abstract, published_at, updated_at, registered_at, authors, image, tags, language, reference, relationships, funding_references, blog_name, content_text, content_html, rid, version"
postsWithConfigSelect = "id, guid, doi, parent_doi, url, archive_url, title, summary, abstract, published_at, updated_at, registered_at, indexed_at, indexed, authors, image, tags, language, reference, relationships, funding_references, blog_name, blog_slug, rid, version, blog: blogs!inner(slug, title, description, feed_url, home_page_url, language, category, status, generator, license, updated_at)"
postsWithBlogSelect = "id, guid, doi, parent_doi, url, archive_url, title, summary, abstract, published_at, updated_at, registered_at, indexed_at, indexed, authors, image, tags, language, reference, relationships, funding_references, blog_name, blog_slug, rid,  version, blog: blogs!inner(*)"
postsWithContentSelect = "id, guid, doi, parent_doi, url, archive_url, title, summary, abstract, content_text, content_html, published_at, updated_at, registered_at, indexed_at, authors, image, tags, language, reference, relationships, funding_references, blog_name, blog_slug, rid, version, blog: blogs!inner(*)"
postsForUpsertSelect = "id, guid, doi, parent_doi, url, archive_url, title, summary, abstract, published_at, updated_at, registered_at, indexed_at, authors, image, tags, language, reference, relationships, funding_references, blog_name, blog_slug, rid, version, blog: blogs!inner(*)"
postsWithCitationsSelect = "id, guid, doi, parent_doi, url, archive_url, title, summary, abstract, content_text, content_html, published_at, updated_at, registered_at, indexed_at, authors, image, tags, language, reference, relationships, funding_references, blog_name, blog_slug, rid, version, blog: blogs!inner(*), citations: citations!inner(citation, unstructured, validated, updated_at, published_at)"
citationsSelect = "citation, unstructured, validated, updated_at, published_at"
citationsWithDoiSelect = "doi, citation, unstructured, validated, updated_at, published_at, type"
citationsWithCidSelect = "cid, doi, citation, unstructured, validated, updated_at, published_at, type"
