"""Simplified PostgreSQL database client for Supabase Pro.

Single connection pool with proper error handling, health checks, and monitoring.
Designed for Supabase Transaction Mode (port 6543) on Pro tier.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)


class DatabaseConfig:
    """Database configuration from environment variables."""

    def __init__(self):
        self.user = os.environ.get("QUART_POSTGRES_USER", "")
        self.password = os.environ.get("QUART_POSTGRES_PASSWORD", "")
        self.host = os.environ.get("QUART_POSTGRES_HOST", "localhost")
        self.port = int(os.environ.get("QUART_POSTGRES_PORT", "6543"))
        self.database = os.environ.get("QUART_POSTGRES_DB", "postgres")

        # Supabase Pro limits - adjust based on your plan
        self.max_connections = int(os.environ.get("DB_MAX_CONNECTIONS", "20"))
        self.min_connections = int(os.environ.get("DB_MIN_CONNECTIONS", "5"))

    @property
    def url(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


class DatabasePool:
    """Single unified connection pool for all database operations."""

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._pool: AsyncConnectionPool | None = None
        self._pool_lock = asyncio.Lock()
        self._health_check_task: asyncio.Task | None = None

    async def initialize(self) -> None:
        """Initialize connection pool with Supabase-optimized settings."""
        async with self._pool_lock:
            if self._pool is not None:
                logger.warning("Pool already initialized")
                return

            logger.info(
                f"Initializing database pool: {self.config.host}:{self.config.port}, "
                f"min={self.config.min_connections}, max={self.config.max_connections}"
            )

            try:
                self._pool = AsyncConnectionPool(
                    self.config.url,
                    min_size=self.config.min_connections,
                    max_size=self.config.max_connections,
                    timeout=30.0,  # Wait up to 30s for connection
                    max_idle=600.0,  # Keep idle connections for 10 min
                    max_lifetime=1800.0,  # Recycle connections after 30 min
                    reconnect_timeout=10.0,  # Quick reconnect attempts
                    check=AsyncConnectionPool.check_connection,  # Validate connections on checkout
                    kwargs={
                        "autocommit": True,  # Autocommit for most operations (use transaction() for multi-statement)
                        "row_factory": dict_row,
                        "prepare_threshold": None,  # Required for Supabase Transaction Mode
                        "keepalives": 1,
                        "keepalives_idle": 30,
                        "keepalives_interval": 10,
                        "keepalives_count": 5,
                        "connect_timeout": 10,
                        "options": "-c statement_timeout=120000 -c idle_in_transaction_session_timeout=120000",
                    },
                    open=False,
                )
                await self._pool.open()

                # Start background health checks
                self._health_check_task = asyncio.create_task(self._health_check_loop())

                logger.info("Database pool initialized successfully")
            except Exception as e:
                self._pool = None
                logger.error(f"Failed to initialize database pool: {e}", exc_info=True)
                raise ConnectionError(f"Database initialization failed: {e}")

    async def close(self) -> None:
        """Close the connection pool gracefully."""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        if self._pool is not None:
            logger.info("Closing database pool")
            await self._pool.close()
            self._pool = None

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[psycopg.AsyncConnection]:
        """Acquire a connection from the pool with automatic release."""
        if self._pool is None:
            raise ConnectionError("Database pool not initialized")

        conn = None
        try:
            conn = await self._pool.getconn()
            yield conn
        except Exception:
            # If an error occurred, check if connection is broken
            if conn is not None and conn.closed:
                logger.warning(f"Discarding broken connection: {conn!r}")
                conn = None  # Don't return broken connection to pool
            raise
        finally:
            if conn is not None:
                await self._pool.putconn(conn)

    async def _health_check_loop(self) -> None:
        """Periodic health check to detect connection issues early."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                async with self.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute("SELECT 1")
                logger.debug("Database health check: OK")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Database health check failed: {e}")

    def get_pool_stats(self) -> Dict[str, Any]:
        """Get current pool statistics for monitoring."""
        if self._pool is None:
            return {"status": "not_initialized"}

        try:
            # psycopg_pool has limited stats API
            # Basic info about pool configuration
            return {
                "status": "active",
                "min_size": self.config.min_connections,
                "max_size": self.config.max_connections,
                "host": self.config.host,
                "port": self.config.port,
                "database": self.config.database,
            }
        except Exception as e:
            logger.error(f"Error getting pool stats: {e}")
            return {"status": "error", "error": str(e)}


# Global pool instance
_db_pool: DatabasePool | None = None


async def get_pool() -> DatabasePool:
    """Get or create the global database pool."""
    global _db_pool
    if _db_pool is None:
        config = DatabaseConfig()
        _db_pool = DatabasePool(config)
        await _db_pool.initialize()
    return _db_pool


async def close_pool() -> None:
    """Close the global database pool."""
    global _db_pool
    if _db_pool is not None:
        await _db_pool.close()
        _db_pool = None


# JSON parameter handling
_JSONB_PARAM_KEYS = {
    "authors",
    "images",
    "reference",
    "relationships",
    "funding_references",
    "archive_timestamps",
}


def _adapt_params(params: Optional[Dict]) -> Dict:
    """Adapt parameters for psycopg, handling JSONB types."""
    if not params:
        return {}

    adapted = {}
    for key, value in params.items():
        if value is None:
            adapted[key] = None
        elif key in _JSONB_PARAM_KEYS and not isinstance(value, Jsonb):
            adapted[key] = Jsonb(value)
        else:
            adapted[key] = value
    return adapted


def _convert_query_syntax(query: str) -> str:
    """Convert buildpg :param syntax to psycopg %(param)s syntax.

    This provides backward compatibility with existing queries using buildpg syntax.
    """
    import re

    # Replace :param with %(param)s, but avoid replacing :: (PostgreSQL cast operator)
    return re.sub(r"(?<!:):(\w+)(?!:)", r"%(\1)s", query)


def _normalize_value(value: Any) -> Any:
    """Normalize DB-returned types to JSON-serializable primitives."""
    if value is None:
        return None
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        try:
            integral = value.to_integral_value()
            if value == integral:
                return int(integral)
        except Exception:
            pass
        return float(value)
    if isinstance(value, dict):
        return {k: _normalize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_value(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_normalize_value(v) for v in value)
    return value


async def execute_with_retry(
    func,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> Any:
    """Execute database operation with automatic retry on connection errors."""
    last_error = None

    for attempt in range(max_retries):
        try:
            return await func()
        except (psycopg.OperationalError, psycopg.InterfaceError) as e:
            last_error = e
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2**attempt)  # Exponential backoff
                logger.warning(
                    f"Database connection error (attempt {attempt + 1}/{max_retries}): {e}. "
                    f"Retrying in {wait_time:.1f}s..."
                )
                # Force pool to check and discard stale connections before retry
                try:
                    pool = await get_pool()
                    if pool._pool is not None:
                        await pool._pool.check()
                        logger.info(
                            "Pool health check completed, stale connections purged"
                        )
                except Exception as check_err:
                    logger.warning(
                        f"Pool health check during retry failed: {check_err}"
                    )
                await asyncio.sleep(wait_time)
            else:
                logger.error(
                    f"Database operation failed after {max_retries} attempts: {e}"
                )
                raise
        except Exception:
            # Don't retry on non-connection errors
            raise

    # Should not reach here, but just in case
    if last_error:
        raise last_error


class Database:
    """Simplified database operations with consistent error handling."""

    @staticmethod
    async def fetch_one(query: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Fetch single row as dictionary."""

        async def _execute():
            pool = await get_pool()
            query_converted = _convert_query_syntax(query)
            async with pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query_converted, _adapt_params(params))
                    row = await cursor.fetchone()
                    return _normalize_value(dict(row)) if row else None

        return await execute_with_retry(_execute)

    @staticmethod
    async def fetch_all(query: str, params: Optional[Dict] = None) -> List[Dict]:
        """Fetch all rows as list of dictionaries."""

        async def _execute():
            pool = await get_pool()
            query_converted = _convert_query_syntax(query)
            async with pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query_converted, _adapt_params(params))
                    rows = await cursor.fetchall()
                    return [_normalize_value(dict(row)) for row in rows]

        return await execute_with_retry(_execute)

    @staticmethod
    async def execute(query: str, params: Optional[Dict] = None) -> None:
        """Execute query (INSERT/UPDATE/DELETE) without returning results."""

        async def _execute():
            pool = await get_pool()
            query_converted = _convert_query_syntax(query)
            async with pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query_converted, _adapt_params(params))
                    # No commit needed - autocommit is enabled

        await execute_with_retry(_execute)

    @staticmethod
    async def execute_many(query: str, params_list: List[Dict]) -> None:
        """Execute query multiple times with different parameters."""
        if not params_list:
            return

        async def _execute():
            pool = await get_pool()
            query_converted = _convert_query_syntax(query)
            async with pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.executemany(
                        query_converted, [_adapt_params(p) for p in params_list]
                    )
                    # No commit needed - autocommit is enabled

        await execute_with_retry(_execute)

    @staticmethod
    @asynccontextmanager
    async def transaction():
        """Context manager for explicit transactions.

        Use this when you need multiple operations to be atomic.
        Temporarily disables autocommit for the transaction duration.
        """
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Temporarily disable autocommit for this transaction
            await conn.set_autocommit(False)
            try:
                yield conn
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
            finally:
                # Re-enable autocommit
                await conn.set_autocommit(True)


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
            WHERE status = ANY(%(statuses)s)
            ORDER BY {order_by}
        """
        return await Database.fetch_all(query, {"statuses": statuses})

    @staticmethod
    async def select_by_slug(slug: str) -> Optional[Dict]:
        """Select single blog by slug."""
        query = """
            SELECT id, slug, feed_url, current_feed_url, home_page_url, 
                   archive_host, archive_collection, archive_timestamps, 
                   feed_format, created_at, updated_at, registered_at, 
                   license, mastodon, generator, generator_raw, language, 
                   favicon, title, description, category, subfield, status, 
                   user_id, authors, use_api, relative_url, filter, secure, 
                   community_id, prefix, issn
            FROM blogs
            WHERE slug = %(slug)s
        """
        return await Database.fetch_one(query, {"slug": slug})

    @staticmethod
    async def update_blog(slug: str, updates: Dict) -> bool:
        """Update blog fields by slug."""
        # Build SET clause dynamically
        set_clauses = [f"{key} = %({key})s" for key in updates.keys()]
        query = f"""
            UPDATE blogs
            SET {', '.join(set_clauses)}, updated_at = EXTRACT(EPOCH FROM NOW())
            WHERE slug = %(slug)s
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
            WHERE p.blog_slug = %(blog_slug)s
            ORDER BY {order_by}
            LIMIT %(limit)s OFFSET %(offset)s
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
            WHERE p.id = %(post_id)s
        """
        return await Database.fetch_one(query, {"post_id": post_id})

    @staticmethod
    async def select_by_doi(doi: str) -> Optional[Dict]:
        """Select single post by DOI with blog data."""
        query = f"""
            SELECT {POSTS_WITH_BLOG_SELECT}
            FROM posts p
            INNER JOIN blogs b ON p.blog_slug = b.slug
            WHERE p.doi = %(doi)s
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
            WHERE doi = %(doi)s
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
            VALUES (%(cid)s, %(doi)s, %(citation)s, %(unstructured)s, %(published_at)s, %(type)s, %(blog_slug)s)
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


# Export commonly used functions
__all__ = [
    "Database",
    "get_pool",
    "close_pool",
    "BlogsQueries",
    "PostsQueries",
    "CitationsQueries",
]
