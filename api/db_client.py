"""PostgreSQL database client using QuartDB."""

from typing import Optional, List, Dict, Any
from quart import g


class Database:
    """Database access wrapper for QuartDB with common query patterns."""

    @staticmethod
    async def fetch_one(query: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Fetch single row as dictionary.

        Args:
            query: SQL query with :param placeholders
            params: Dictionary of parameter values

        Returns:
            Dictionary of column:value or None if no rows found
        """
        row = await g.connection.fetch_first(query, params or {})
        return dict(row) if row else None

    @staticmethod
    async def fetch_all(query: str, params: Optional[Dict] = None) -> List[Dict]:
        """Fetch all rows as list of dictionaries.

        Args:
            query: SQL query with :param placeholders
            params: Dictionary of parameter values

        Returns:
            List of dictionaries, empty list if no rows found
        """
        rows = await g.connection.fetch_all(query, params or {})
        return [dict(row) for row in rows]

    @staticmethod
    async def execute(query: str, params: Optional[Dict] = None) -> Any:
        """Execute query (INSERT/UPDATE/DELETE) and return result.

        Args:
            query: SQL query with :param placeholders
            params: Dictionary of parameter values

        Returns:
            Execution result (row count, etc.)
        """
        return await g.connection.execute(query, params or {})

    @staticmethod
    async def execute_many(query: str, params_list: List[Dict]) -> Any:
        """Execute query multiple times with different parameters.

        Args:
            query: SQL query with :param placeholders
            params_list: List of parameter dictionaries

        Returns:
            Execution result
        """
        return await g.connection.execute_many(query, params_list)


# Common select field sets (matching supabase_client.py)
BLOGS_SELECT = """
    slug, title, description, language, favicon, feed_url, 
    feed_format, home_page_url, generator, category, subfield
"""

POSTS_SELECT = """
    guid, doi, parent_doi, url, title, summary, abstract, 
    published_at, updated_at, registered_at, authors, image, 
    tags, language, reference, relationships, funding_references, 
    blog_name, content_html, rid, version
"""

POSTS_WITH_BLOG_SELECT = """
    p.id, p.guid, p.doi, p.parent_doi, p.url, p.archive_url, 
    p.title, p.summary, p.abstract, p.published_at, p.updated_at, 
    p.registered_at, p.indexed_at, p.indexed, p.authors, p.image, 
    p.tags, p.language, p.reference, p.relationships, 
    p.funding_references, p.blog_name, p.blog_slug, p.rid, p.version,
    row_to_json(b.*) as blog
"""

CITATIONS_SELECT = """
    citation, unstructured, validated, updated_at, published_at
"""


# Query builder helpers for common patterns
class BlogsQueries:
    """Pre-built queries for blogs table."""

    @staticmethod
    async def select_all(
        statuses: List[str] = None, order_by: str = "slug"
    ) -> List[Dict]:
        """Select all blogs with optional status filter."""
        statuses = statuses or ["active", "expired", "archived"]
        query = f"""
            SELECT {BLOGS_SELECT}
            FROM blogs
            WHERE status = ANY(:statuses)
            ORDER BY {order_by}
        """
        return await Database.fetch_all(query, {"statuses": statuses})

    @staticmethod
    async def select_by_slug(slug: str) -> Optional[Dict]:
        """Select single blog by slug."""
        query = f"""
            SELECT id, slug, feed_url, current_feed_url, home_page_url, 
                   archive_host, archive_collection, archive_timestamps, 
                   feed_format, created_at, updated_at, registered_at, 
                   license, mastodon, generator, generator_raw, language, 
                   favicon, title, description, category, subfield, status, 
                   user_id, authors, use_api, relative_url, filter, secure, 
                   community_id, prefix, issn
            FROM blogs
            WHERE slug = :slug
        """
        return await Database.fetch_one(query, {"slug": slug})

    @staticmethod
    async def update_blog(slug: str, updates: Dict) -> bool:
        """Update blog fields by slug."""
        # Build SET clause dynamically
        set_clauses = [f"{key} = :{key}" for key in updates.keys()]
        query = f"""
            UPDATE blogs
            SET {', '.join(set_clauses)}, updated_at = EXTRACT(EPOCH FROM NOW())
            WHERE slug = :slug
        """
        params = {**updates, "slug": slug}
        await Database.execute(query, params)
        return True


class PostsQueries:
    """Pre-built queries for posts table."""

    @staticmethod
    async def select_by_blog(
        blog_slug: str,
        limit: int = 10,
        offset: int = 0,
        order_by: str = "published_at DESC",
    ) -> List[Dict]:
        """Select posts by blog slug with blog data joined."""
        query = f"""
            SELECT {POSTS_WITH_BLOG_SELECT}
            FROM posts p
            INNER JOIN blogs b ON p.blog_slug = b.slug
            WHERE p.blog_slug = :blog_slug
            ORDER BY {order_by}
            LIMIT :limit OFFSET :offset
        """
        return await Database.fetch_all(
            query, {"blog_slug": blog_slug, "limit": limit, "offset": offset}
        )

    @staticmethod
    async def select_by_id(post_id: str) -> Optional[Dict]:
        """Select single post by ID with blog data."""
        query = f"""
            SELECT {POSTS_WITH_BLOG_SELECT}
            FROM posts p
            INNER JOIN blogs b ON p.blog_slug = b.slug
            WHERE p.id = :post_id
        """
        return await Database.fetch_one(query, {"post_id": post_id})

    @staticmethod
    async def select_by_doi(doi: str) -> Optional[Dict]:
        """Select single post by DOI with blog data."""
        query = f"""
            SELECT {POSTS_WITH_BLOG_SELECT}
            FROM posts p
            INNER JOIN blogs b ON p.blog_slug = b.slug
            WHERE p.doi = :doi
        """
        return await Database.fetch_one(query, {"doi": doi})


class CitationsQueries:
    """Pre-built queries for citations table."""

    @staticmethod
    async def select_by_doi(doi: str, validated_only: bool = True) -> List[Dict]:
        """Select citations for a DOI."""
        query = f"""
            SELECT {CITATIONS_SELECT}
            FROM citations
            WHERE doi = :doi
        """
        if validated_only:
            query += " AND validated = true"
        query += " ORDER BY published_at, updated_at"

        return await Database.fetch_all(query, {"doi": doi})

    @staticmethod
    async def upsert_citation(citation: Dict) -> Optional[Dict]:
        """Upsert a single citation using ON CONFLICT."""
        query = """
            INSERT INTO citations (cid, doi, citation, unstructured, published_at, type, blog_slug)
            VALUES (:cid, :doi, :citation, :unstructured, :published_at, :type, :blog_slug)
            ON CONFLICT (cid) DO UPDATE SET
                doi = EXCLUDED.doi,
                citation = EXCLUDED.citation,
                unstructured = EXCLUDED.unstructured,
                published_at = EXCLUDED.published_at,
                type = EXCLUDED.type,
                blog_slug = EXCLUDED.blog_slug,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
        """
        return await Database.fetch_one(query, citation)
