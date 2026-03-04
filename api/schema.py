from dataclasses import dataclass, field
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
    """Blog schema — mirrors the public.blogs table."""

    slug: str
    title: str | None = None
    description: str | None = None
    language: str | None = None
    favicon: str | None = None
    feed_url: str | None = None
    current_feed_url: str | None = None
    feed_format: str | None = None
    home_page_url: str | None = None
    generator: str | None = None
    generator_raw: str | None = None
    category: str | None = None
    subfield: str | None = None
    subfield_validated: bool | None = None
    prefix: str | None = None
    status: str | None = None
    license: str | None = None
    issn: str | None = None
    authors: list = field(default_factory=list)
    funding: dict | None = None
    user_id: str | None = None
    community_id: str | None = None
    ror: str | None = None
    mastodon: str | None = None
    use_mastodon: bool = False
    use_api: bool | None = None
    relative_url: str | None = None
    canonical_url: bool | None = None
    filter: str | None = None
    secure: bool = True
    archive_prefix: str | None = None
    archive_collection: int | None = None
    archive_timestamps: list | None = None
    archive_host: str | None = None
    registered_at: int = 0
    created_at: float | None = None
    updated_at: float | None = None
    indexed: bool = True
    doi_as_guid: bool = False
    id: str | None = None
    items: list = field(default_factory=list)


@dataclass
class Citation:
    """Citation schema — mirrors the public.citations table."""

    doi: str
    citation: str
    validated: bool = True
    updated_at: datetime | None = None
    published_at: str | None = None
    cid: str | None = None
    unstructured: str | None = None
    type: str | None = None
    cito: list = field(default_factory=list)
    blog_slug: str | None = None


@dataclass
class Post:
    """Post schema — mirrors the public.posts table."""

    guid: str
    url: str
    title: str
    blog_slug: str
    doi: str | None = None
    parent_doi: str | None = None
    rid: str | None = None
    archive_url: str | None = None
    summary: str | None = None
    abstract: str | None = None
    content_html: str | None = None
    published_at: float | None = None
    updated_at: float | None = None
    registered_at: int = 0
    indexed_at: float = 0
    indexed: bool = True
    registered: bool = True
    archived: bool = False
    has_content: bool = False
    authors: list = field(default_factory=list)
    image: str | None = None
    tags: list = field(default_factory=list)
    language: str | None = None
    reference: list = field(default_factory=list)
    relationships: list = field(default_factory=list)
    funding_references: list | None = None
    images: list = field(default_factory=list)
    blog_name: str | None = None
    category: str | None = None
    subfield: str | None = None
    topic: str | None = None
    topic_score: float = 0
    topic_validated: bool | None = None
    status: str = "active"
    version: str | None = None
    id: str | None = None
    blog: dict | None = None


@dataclass
class Work:
    """Work schema."""

    id: str
    url: str
    titles: list = field(default_factory=list)
    contributors: list = field(default_factory=list)
    language: str | None = None
    references: list = field(default_factory=list)
    relations: list = field(default_factory=list)
