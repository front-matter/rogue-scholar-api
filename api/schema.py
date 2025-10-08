from dataclasses import dataclass
from datetime import datetime


@dataclass
class PostQuery:
    """Query parameters for posts."""

    query: str | None = None
    tags: str | None = None
    language: str | None = None
    page: int | None = 1
    per_page: int | None = 10
    sort: str | None = None
    order: str | None = None
    include_fields: str | None = None
    blog_slug: str | None = None


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
    funding: str
    items: list


@dataclass
class Citation:
    """Citation schema."""

    id: str
    doi: str
    citation: str
    validated: bool
    updated_at: datetime
    published_at: str


@dataclass
class Post:
    """Post schema."""

    id: str
    guid: str
    doi: str
    rid: str
    url: str
    archive_url: str
    title: str
    summary: str
    content_html: str
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


@dataclass
class Work:
    """Work schema."""

    id: str
    url: str
    titles: list
    contributors: list
    language: str
    references: list
    relations: list
