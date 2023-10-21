import feedparser
import socket
from commonmeta.utils import wrap

from rogue_scholar_api.supabase import (
    supabase_client as supabase,
    supabase_admin_client as supabase_admin,
)
from rogue_scholar_api.utils import start_case, get_date, unix_timestamp


def extract_single_blog(slug: str):
    """Extract a single blog."""
    response = (
        supabase.table("blogs")
        .select(
            "id, slug, feed_url, current_feed_url, home_page_url, archive_prefix, feed_format, created_at, updated_at, use_mastodon, generator, language, favicon, title, description, category, status, user_id, authors, plan, use_api, relative_url, filter"
        )
        .eq("slug", slug)
        .maybe_single()
        .execute()
    )
    if not response.data:
        return None
    config = response.data
    socket.setdefaulttimeout(60)
    parsed = feedparser.parse(response.data["feed_url"])
    feed = parsed.feed
    home_page_url = feed.get("link", None) or config["home_page_url"]
    updated_at = get_date(feed.get("updated", None))
    if updated_at:
        updated_at = unix_timestamp(updated_at) or config["updated_at"]

    feed_format = parse_feed_format(feed) or config["feed_format"]
    title = feed.get("title", None) or config["title"]
    generator = (
        parse_generator(feed.get("generator_detail", None) or feed.get("generator"))
        or config["generator"]
    )
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
        "feed_url": config["feed_url"],
        "created_at": config["created_at"],
        "updated_at": updated_at,
        "current_feed_url": config["current_feed_url"],
        "home_page_url": home_page_url,
        "archive_prefix": config["archive_prefix"],
        "feed_format": feed_format,
        "title": title,
        "generator": generator,
        "description": description,
        "favicon": favicon,
        "language": language,
        "license": "https://creativecommons.org/licenses/by/4.0/legalcode",
        "category": config["category"],
        "status": config["status"],
        "plan": config["plan"],
        "user_id": config["user_id"],
        "authors": config["authors"],
        "use_mastodon": config["use_mastodon"],
        "use_api": config["use_api"],
        "relative_url": config["relative_url"],
        "filter": config["filter"],
    }
    return upsert_single_blog(blog)


def parse_generator(generator):
    """Parse blog generator."""
    if not generator:
        return None
    elif isinstance(generator, dict):
        version = generator.get("version", None)
        name = generator.get("name", None)
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

        if name == "Site Server":
            name = "Squarespace"

        return name + f" {version}" if version else name
    if generator == "Wowchemy (https://wowchemy.com)":
        return "Hugo"
    return generator.capitalize()


def parse_feed_format(feed):
    """Parse feed format."""
    links = feed.get("links", [])
    if not links:
        return "application/feed+json"
    return next(
        (link["type"] for link in wrap(links) if link["rel"] == "self"),
        None,
    )


def upsert_single_blog(blog):
    """Upsert single blog."""

    # find timestamp from last modified post
    response = (
        supabase.table("posts")
        .select("updated_at, blog_slug")
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
            .upsert(
                {
                    "id": blog.get("id", None),
                    "slug": blog.get("slug", None),
                    "title": blog.get("title", None),
                    "description": blog.get("description", None),
                    "feed_url": blog.get("feed_url", None),
                    "current_feed_url": blog.get("current_feed_url", None),
                    "home_page_url": blog.get("home_page_url", None),
                    "feed_format": blog.get("feed_format", None),
                    "modified_at": blog.get("modified_at", None),
                    "updated_at": blog.get("updated_at", None),
                    "language": blog.get("language", None),
                    "category": blog.get("category", None),
                    "favicon": blog.get("favicon", None),
                    "license": blog.get("license", None),
                    "generator": blog.get("generator", None),
                    "status": blog.get("status", None),
                    "user_id": blog.get("user_id", None),
                    "use_mastodon": blog.get("use_mastodon", None),
                },
                returning="representation",
                ignore_duplicates=False,
                on_conflict="slug",
            )
            .execute()
        )
        return response.data[0]
    except Exception as error:
        print(error)
        return None
