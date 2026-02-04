"""PostgreSQL database client.

Primarily uses QuartDB's request-scoped connection via ``quart.g.connection``.
If no request/app context connection is present (e.g. in scripts), it falls
back to a module-level psycopg connection pool.
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import date, datetime
from decimal import Decimal
from quart import g

from buildpg import BuildError, render
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool


_pool: AsyncConnectionPool | None = None
_pool_lock = asyncio.Lock()


def _database_url_from_env() -> str:
    user = os.environ.get("QUART_POSTGRES_USER", "")
    password = os.environ.get("QUART_POSTGRES_PASSWORD", "")
    host = os.environ.get("QUART_POSTGRES_HOST", "localhost")
    port = os.environ.get("QUART_POSTGRES_PORT", "5432")
    db = os.environ.get("QUART_POSTGRES_DB", "postgres")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


async def _check_connection(connection):
    """Validate that a pooled connection is still alive."""
    try:
        await connection.execute("SELECT 1")
    except Exception:
        # Connection is dead, will be discarded by pool
        raise psycopg.OperationalError("Connection check failed")


async def _get_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is not None:
        return _pool

    async with _pool_lock:
        if _pool is not None:
            return _pool

        _pool = AsyncConnectionPool(
            _database_url_from_env(),
            min_size=0,
            max_size=3,
            timeout=60.0,
            max_idle=300.0,
            reconnect_timeout=30.0,
            check=AsyncConnectionPool.check_connection,
            kwargs={
                "autocommit": True,
                "cursor_factory": psycopg.AsyncRawCursor,
                "row_factory": dict_row,
                "keepalives": 1,
                "keepalives_idle": 30,
                "keepalives_interval": 10,
                "keepalives_count": 5,
                "connect_timeout": 10,
            },
            open=False,
        )
        await _pool.open()
        return _pool


def _compile(query: str, params: Optional[Dict] = None) -> tuple[str, list[Any]]:
    try:
        return render(query, **(params or {}))
    except BuildError as error:
        raise ValueError(str(error))


_JSONB_PARAM_KEYS = {
    # posts
    "authors",
    "images",
    "reference",
    "relationships",
    "funding_references",
    # blogs
    "archive_timestamps",
    "authors",
}


def _adapt_params_for_psycopg(params: Optional[Dict]) -> Dict:
    if not params:
        return {}

    adapted: Dict[str, Any] = {}
    for key, value in params.items():
        if value is None:
            adapted[key] = None
            continue

        if key in _JSONB_PARAM_KEYS and not isinstance(value, Jsonb):
            adapted[key] = Jsonb(value)
            continue

        adapted[key] = value

    return adapted


def _normalize_db_value(value: Any) -> Any:
    """Normalize DB-returned types into JSON-friendly Python primitives.

    Quart's `jsonify` cannot serialize some DB-native types (e.g. UUID, Decimal).
    This keeps API responses stable by converting to strings/numbers.
    """

    if value is None:
        return None

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    # Postgres NUMERIC -> Decimal
    if isinstance(value, Decimal):
        try:
            integral = value.to_integral_value()
            if value == integral:
                return int(integral)
        except Exception:
            pass
        return float(value)

    if isinstance(value, dict):
        return {k: _normalize_db_value(v) for k, v in value.items()}

    if isinstance(value, list):
        return [_normalize_db_value(v) for v in value]

    if isinstance(value, tuple):
        return tuple(_normalize_db_value(v) for v in value)

    return value


class Database:
    """Database access wrapper for QuartDB with common query patterns."""

    @staticmethod
    def _g_connection():
        return getattr(g, "connection", None)

    @staticmethod
    async def fetch_one(query: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Fetch single row as dictionary.

        Args:
            query: SQL query with :param placeholders
            params: Dictionary of parameter values

        Returns:
            Dictionary of column:value or None if no rows found
        """
        connection = Database._g_connection()
        if connection is not None:
            row = await connection.fetch_first(
                query, _adapt_params_for_psycopg(params or {})
            )
            return _normalize_db_value(dict(row)) if row else None

        pool = await _get_pool()
        compiled_query, args = _compile(query, _adapt_params_for_psycopg(params))
        conn = await pool.getconn()
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(compiled_query, args)
                row = await cursor.fetchone()
        finally:
            await pool.putconn(conn)
        return _normalize_db_value(dict(row)) if row else None

    @staticmethod
    async def fetch_all(query: str, params: Optional[Dict] = None) -> List[Dict]:
        """Fetch all rows as list of dictionaries.

        Args:
            query: SQL query with :param placeholders
            params: Dictionary of parameter values

        Returns:
            List of dictionaries, empty list if no rows found
        """
        connection = Database._g_connection()
        if connection is not None:
            rows = await connection.fetch_all(
                query, _adapt_params_for_psycopg(params or {})
            )
            return [_normalize_db_value(dict(row)) for row in rows]

        pool = await _get_pool()
        compiled_query, args = _compile(query, _adapt_params_for_psycopg(params))
        conn = await pool.getconn()
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(compiled_query, args)
                rows = await cursor.fetchall()
        finally:
            await pool.putconn(conn)
        return [_normalize_db_value(dict(row)) for row in rows]

    @staticmethod
    async def execute(query: str, params: Optional[Dict] = None) -> Any:
        """Execute query (INSERT/UPDATE/DELETE) and return result.

        Args:
            query: SQL query with :param placeholders
            params: Dictionary of parameter values

        Returns:
            Execution result (row count, etc.)
        """
        connection = Database._g_connection()
        if connection is not None:
            return await connection.execute(query, _adapt_params_for_psycopg(params))

        pool = await _get_pool()
        compiled_query, args = _compile(query, _adapt_params_for_psycopg(params))
        conn = await pool.getconn()
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(compiled_query, args)
        finally:
            await pool.putconn(conn)
        return None

    @staticmethod
    async def execute_many(query: str, params_list: List[Dict]) -> Any:
        """Execute query multiple times with different parameters.

        Args:
            query: SQL query with :param placeholders
            params_list: List of parameter dictionaries

        Returns:
            Execution result
        """
        connection = Database._g_connection()
        if connection is not None:
            return await connection.execute_many(
                query, [_adapt_params_for_psycopg(p) for p in params_list]
            )

        if not params_list:
            return None

        pool = await _get_pool()
        compiled_query, first_args = _compile(
            query, _adapt_params_for_psycopg(params_list[0])
        )
        args_list = [first_args] + [
            _compile(query, _adapt_params_for_psycopg(p))[1] for p in params_list[1:]
        ]
        conn = await pool.getconn()
        try:
            async with conn.cursor() as cursor:
                await cursor.executemany(compiled_query, args_list)
        finally:
            await pool.putconn(conn)
        return None


# Common select field sets
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
        statuses: Optional[List[str]] = None, order_by: str = "slug"
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
