"""Blogs module."""
import socket
import asyncio
from typing import Optional
import requests
import feedparser
import re
from bs4 import BeautifulSoup as bs4
from furl import furl

from api.supabase import (
    supabase_client as supabase,
    supabase_admin_client as supabase_admin,
)
from api.utils import (
    start_case,
    get_date,
    unix_timestamp,
    wrap,
    normalize_url,
    is_valid_url,
)


async def find_feed(url: str) -> Optional[str]:
    """Find RSS feed in homepage. Based on https://gist.github.com/alexmill/9bc634240531d81c3abe
    Prefer JSON Feed over Atom over RSS"""
    url = normalize_url(url)
    raw = requests.get(url).text
    html = bs4(raw, features="lxml")
    feeds = html.findAll("link", rel="alternate")
    if len(feeds) == 0:
        return None
    feed_url = next(
        (
            feed.get("href", None)
            for feed in feeds
            if feed.get("type", None) == "application/feed+json"
        ),
        None,
    )
    if feed_url is None:
        feed_url = next(
            (
                feed.get("href", None)
                for feed in feeds
                if feed.get("type", None) == "application/atom+xml"
            ),
            None,
        )
    if feed_url is None:
        feed_url = next(
            (
                feed.get("href", None)
                for feed in feeds
                if feed.get("type", None) == "application/rss+xml"
            ),
            None,
        )
    if is_valid_url(feed_url):
        return feed_url
    # else feed_url is relative url
    f = furl(url)
    f.path = feed_url
    return f.url


async def extract_all_blogs():
    """Extract all blogs."""

    blogs = (
        supabase.table("blogs")
        .select("slug")
        .in_("status", ["approved", "active"])
        .order("title", desc=False)
        .execute()
    )
    tasks = []
    for blog in blogs.data:
        task = extract_single_blog(blog["slug"])
        tasks.append(task)

    results = await asyncio.gather(*tasks)
    return results


async def extract_single_blog(slug: str):
    """Extract a single blog."""
    response = (
        supabase.table("blogs")
        .select(
            "id, slug, feed_url, current_feed_url, home_page_url, archive_prefix, feed_format, created_at, updated_at, mastodon, generator_raw, language, favicon, title, description, category, status, user_id, authors, plan, use_api, relative_url, filter, secure"
        )
        .eq("slug", slug)
        .maybe_single()
        .execute()
    )
    if not response.data:
        return None
    config = response.data
    feed_url = config.get("feed_url", None)
    if feed_url is None:
        feed_url = await find_feed(config["home_page_url"])
    socket.setdefaulttimeout(60)
    parsed = feedparser.parse(config.get("feed_url", None) or feed_url)
    feed = parsed.feed
    home_page_url = config["home_page_url"] or feed.get("link", None)
    updated_at = get_date(feed.get("updated", None))
    if updated_at:
        updated_at = unix_timestamp(updated_at) or config["updated_at"]

    feed_format = parse_feed_format(feed) or config["feed_format"]
    title = feed.get("title", None) or config["title"]
    generator_raw = (
        parse_generator(feed.get("generator_detail", None) or feed.get("generator"))
        or config["generator_raw"]
        or "Other"
    )
    generator = re.split(" ", generator_raw)[0]
    description = feed.get("subtitle", None) or config["description"]
    favicon = feed.get("icon", None) or config["favicon"]

    # ignore the default favicons
    if favicon in ["https://s0.wp.com/i/buttonw-com.png"]:
        favicon = None
    language = feed.get("language", None) or config["language"]
    if language:
        language = language.split("-")[0]

    blog = {
        "id": config["id"],
        "slug": slug,
        "version": "https://jsonfeed.org/version/1.1",
        "feed_url": feed_url,
        "created_at": config["created_at"],
        "updated_at": updated_at,
        "current_feed_url": config["current_feed_url"],
        "home_page_url": home_page_url,
        "archive_prefix": config["archive_prefix"],
        "feed_format": feed_format,
        "title": title,
        "generator": generator,
        "generator_raw": generator_raw,
        "description": description,
        "favicon": favicon,
        "language": language,
        "license": "https://creativecommons.org/licenses/by/4.0/legalcode",
        "category": config["category"],
        "status": config["status"],
        "plan": config["plan"],
        "user_id": config["user_id"],
        "authors": config["authors"],
        "mastodon": config["mastodon"],
        "use_api": config["use_api"],
        "relative_url": config["relative_url"],
        "filter": config["filter"],
        "secure": config["secure"],
    }
    blog = update_single_blog(blog)
    return blog


def parse_generator(generator):
    """Parse blog generator."""
    if not generator:
        return None
    elif isinstance(generator, str):
        return generator
    elif isinstance(generator, dict):
        version = generator.get("version", None)
        name = generator.get("name", None)
        if is_valid_url(name):
            f = furl(name)
            name = f.host.split(".")[0]
            version = f.args.get("v", None)

        names = name.split(" ")

        # split name and version
        if len(names) > 1:
            name = names[0]
            version = names[1].split("-")[0]
            if version.startswith("v"):
                version = version[1:]
        name = name.replace("-", " ")

        # capitalize first letter without lowercasing the rest
        name = start_case(name)

        # versions prior to 6.1
        if name == "Wordpress":
            name = "WordPress"

        elif name == "Wowchemy":
            name = "Hugo"
        elif name == "Site Server":
            name = "Squarespace"

        return name + f" {version}" if version else name


def parse_feed_format(feed):
    """Parse feed format."""
    links = feed.get("links", [])
    if not links:
        return "application/feed+json"
    return next(
        (link["type"] for link in wrap(links) if link["rel"] == "self"),
        None,
    )


def update_single_blog(blog):
    """Update single blog."""

    # find timestamp from last updated post
    response = (
        supabase.table("posts")
        .select("updated_at")
        .eq("blog_slug", blog.get("slug"))
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )

    blog["updated_at"] = (
        response.data
        and response.data[0]
        and response.data[0].get("updated_at", 0)
        or 0
    )

    try:
        response = (
            supabase_admin.table("blogs")
            .update(
                {
                    "title": blog.get("title", None),
                    "description": blog.get("description", None),
                    "feed_url": blog.get("feed_url", None),
                    "current_feed_url": blog.get("current_feed_url", None),
                    "home_page_url": blog.get("home_page_url", None),
                    "feed_format": blog.get("feed_format", None),
                    "updated_at": blog.get("updated_at", None),
                    "language": blog.get("language", None),
                    "category": blog.get("category", None),
                    "favicon": blog.get("favicon", None),
                    "license": blog.get("license", None),
                    "generator": blog.get("generator", None),
                    "generator_raw": blog.get("generator_raw", None),
                    "status": blog.get("status", None),
                    "user_id": blog.get("user_id", None),
                    "mastodon": blog.get("mastodon", None),
                    "secure": blog.get("secure", None),
                }
            )
            .eq("slug", blog.get("slug"))
            .execute()
        )
        return response.data[0]
    except Exception as error:
        print(error)
        return None
