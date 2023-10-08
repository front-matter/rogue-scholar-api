from dataclasses import dataclass
from datetime import datetime


@dataclass
class PostQuery:
    query: str
    tags: str
    language: str
    page: int


@dataclass
class Blog:
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
    backlog: int
    prefix: str
    status: str
    plan: str
    funding: str
    items: list


@dataclass
class Post:
    id: str
    doi: str
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
