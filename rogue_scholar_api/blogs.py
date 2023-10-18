import feedparser
import socket
from commonmeta.utils import wrap

from rogue_scholar_api.supabase import (
    supabase_client as supabase,
)
from rogue_scholar_api.utils import start_case


def extract_single_blog(slug: str):
    """Extract a single blog."""
    response = (
        supabase.table("blogs")
        .select(
            "id, slug, feed_url, current_feed_url, home_page_url, archive_prefix, feed_format, created_at, modified_at, use_mastodon, generator, favicon, title, description, category, status, user_id, authors, plan, use_api, relative_url, filter"
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
    modified_at = feed.get("updated", None) or config["modified_at"]

    feed_format = parse_feed_format(feed) or config["feed_format"]
    title = feed.get("title", None) or config["title"]
    generator = (
        parse_generator(feed.get("generator_detail", None)) or config["generator"]
    )
    description = feed.get("subtitle", None) or config["description"]
    favicon = feed.get("icon", None) or config["favicon"]

    # ignore the default favicons
    if favicon in ["https://s0.wp.com/i/buttonw-com.png"]:
        favicon = None
    language = feed.get("language", "en").split("-")[0] or config["language"]

    blog = {
        "id": config["id"],
        "slug": slug,
        "version": "https://jsonfeed.org/version/1.1",
        "feed_url": config["feed_url"],
        "created_at": config["created_at"],
        "modified_at": modified_at,
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
    return blog


def parse_generator(generator):
    """Parse blog generator."""
    if isinstance(generator, dict):
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
    elif isinstance(generator, str):
        if generator == "Wowchemy (https://wowchemy.com)":
            return "Hugo"
        return generator.capitalize()
    else:
        return None


def parse_feed_format(feed):
    """Parse feed format."""
    links = feed.get("links", [])
    if not links:
        return "application/feed+json"
    return next(
        (link["type"] for link in wrap(links) if link["rel"] == "self"),
        None,
    )
