from typing import Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class PostQuery:
    """Query parameters for posts."""

    query: Optional[str] = None
    tags: Optional[str] = None
    language: Optional[str] = None
    page: Optional[int] = 1
    per_page: Optional[int] = 10
    sort: Optional[str] = None
    order: Optional[str] = None
    include_fields: Optional[str] = None
    blog_slug: Optional[str] = None


@dataclass
class Blog:
    """Blog schema."""

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
    prefix: str
    status: str
    plan: str
    funding: str
    items: list


@dataclass
class Post:
    """Post schema."""

    id: str
    guid: str
    doi: str
    url: str
    archive_url: str
    title: str
    summary: str
    content_text: str
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
