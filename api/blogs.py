"""Blogs module."""

import socket
import asyncio
from os import environ
from typing import Optional
import httpx
import ssl
import feedparser
import re
from bs4 import BeautifulSoup as bs4
from furl import furl
import datetime
import pydash as py_
from commonmeta import get_date_from_unix_timestamp, get_language

from api.supabase_client import (
    supabase_client as supabase,
    supabase_admin_client as supabase_admin,
)
from api.utils import (
    compact,
    start_case,
    get_date,
    unix_timestamp,
    wrap,
    normalize_url,
    is_valid_url,
    is_local,
    FOS_MAPPINGS,
)


async def find_feed(url: str) -> Optional[str]:
    """Find RSS feed in homepage. Based on https://gist.github.com/alexmill/9bc634240531d81c3abe
    Prefer JSON Feed over Atom over RSS"""
    url = normalize_url(url)
    raw = httpx.get(url, follow_redirects=True).text
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
        .in_("status", ["approved", "active", "archived"])
        .order("slug", desc=False)
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
            "id, slug, feed_url, current_feed_url, home_page_url, archive_prefix, feed_format, created_at, updated_at, registered_at, license, mastodon, generator_raw, language, favicon, title, description, category, status, user_id, authors, use_api, relative_url, filter, secure, community_id, prefix, issn, feed_format"
        )
        .eq("slug", slug)
        .maybe_single()
        .execute()
    )
    if not response.data:
        return None
    config = response.data
    feed_url = config.get("feed_url", None)
    print(f"Extracting {slug} from {feed_url}")
    if feed_url is None:
        feed_url = await find_feed(config["home_page_url"])
    socket.setdefaulttimeout(60)
    try:
        parsed = feedparser.parse(config.get("feed_url", None) or feed_url)
        feed = parsed.feed
        home_page_url = config["home_page_url"] or feed.get("link", None)
        updated_at = get_date(feed.get("updated", None))
        if updated_at:
            updated_at = unix_timestamp(updated_at) or config["updated_at"]

        feed_format = parse_feed_format(feed) or config["feed_format"]
        title = feed.get("title", None) or config["title"]
        generator_raw = config["generator_raw"] or (
            parse_generator(feed.get("generator_detail", None) or feed.get("generator")) 
            or "Other"
        )
        generator = re.split(" ", generator_raw)[0]
        description = feed.get("subtitle", None) or config["description"]
        if description is not None:
            description = bs4(description, "html.parser").get_text()
        favicon = config["favicon"] or feed.get("icon", None)

        # ignore the default favicons
        if favicon in ["https://s0.wp.com/i/buttonw-com.png"]:
            favicon = None
        language = feed.get("language", None) or config["language"]
        if language:
            language = language.split("-")[0]
    except Exception as error:
        print(error)

        home_page_url = config["home_page_url"]
        updated_at = config["updated_at"] or 0
        feed_format = config["feed_format"]
        title = config["title"]
        generator = config["generator"]
        generator_raw = config["generator_raw"]
        favicon = config["favicon"]
        language = config["language"]

    blog = {
        "id": config["id"],
        "slug": slug,
        "feed_url": feed_url,
        "created_at": config["created_at"],
        "updated_at": updated_at,
        "registered_at": config["registered_at"],
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
        "license": config["license"],
        "category": config["category"],
        "status": config["status"],
        "user_id": config["user_id"],
        "authors": config["authors"],
        "mastodon": config["mastodon"],
        "use_api": config["use_api"],
        "relative_url": config["relative_url"],
        "filter": config["filter"],
        "secure": config["secure"],
        "community_id": config["community_id"],
        "prefix": config["prefix"],
        "issn": config["issn"],
        "feed_format": config["feed_format"],
    }
    update_single_blog(blog)
    
    # update InvenioRDM blog community if blog is active or archived
    if config["status"] in ["active", "archived"]:
        r = upsert_blog_community(blog)
        if r:
            result = py_.pick(
                r.json(),
                ["slug", "metadata.title", "metadata.description", "metadata.website"],
            )
            if blog.get("favicon", None) is not None:
                upload_blog_logo(blog)
                result["logo"] = blog.get("favicon")

            # fetch community id and store it in the blog
            community_id = blog.get("community_id", None)
            if blog.get("community_id", None) is None:
                community_id = push_blog_community_id(slug)

            result["community_id"] = community_id
        else:
            result = r
        return result
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
                    "registered_at": blog.get("registered_at", None),
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


def push_blog_community_id(slug):
    """Get InvenioRDM blog community id and store in blog."""
    try:
        context = ssl.create_default_context()
        if is_local():
            context = False
        url = f"{environ['QUART_INVENIORDM_API']}/api/communities?q=slug:{slug}"
        headers = {"Authorization": f"Bearer {environ['QUART_INVENIORDM_TOKEN']}"}
        response = httpx.get(url, headers=headers, timeout=10,verify=context)
        result = response.json()
        if py_.get(result, "hits.total") != 1:
            return result
        community_id = py_.get(result, "hits.hits[0].id")
        blog_to_update = (
            supabase_admin.table("blogs")
            .update(
                {
                    "community_id": community_id,
                }
            )
            .eq("slug", slug)
            .execute()
        )
        if len(blog_to_update.data) > 0:
            return community_id
    except Exception as error:
        print(error)
        return None


def upsert_blog_community(blog):
    """Upsert an InvenioRDM blog community."""
    if blog.get("community_id", None) is None:
        response = create_blog_community(blog)
    else:
        response = update_blog_community(blog)
    return response


def create_blog_community(blog):
    """Create an InvenioRDM blog community."""
    try:
        context = ssl.create_default_context()
        if is_local():
            context = False
        url = f"{environ['QUART_INVENIORDM_API']}/api/communities"
        headers = {"Authorization": f"Bearer {environ['QUART_INVENIORDM_TOKEN']}"}
        metadata = {
            "title": blog.get("title"),
            "type": {"id": "blog"},
            "website": blog.get("home_page_url"),
        }
        if blog.get("description", None):
            metadata["description"] = py_.truncate(
                blog.get("description", None), 250, omission="", separator=" "
            )
        custom_fields = compact({
            "rs:feed_url": blog.get("feed_url"),
            "rs:feed_format": blog.get("feed_format"),
            "rs:generator": blog.get("generator"),
            "rs:license": blog.get("license"),
            "rs:issn": blog.get("issn"),
            "rs:prefix": blog.get("prefix"),
            "rs:joined": get_date_from_unix_timestamp(blog.get("created_at", 0)),
            "rs:language": get_language(blog.get("language"), format="name"),
            "rs:category": FOS_MAPPINGS.get(blog.get("category"), None),
        })
        data = {
            "access": {
                "visibility": "public",
                "member_policy": "open",
                "record_policy": "open",
                "review_policy": "open",
            },
            "slug": blog.get("slug"),
            "metadata": metadata,
            "custom_fields": custom_fields,
        }
        response = httpx.post(url, headers=headers, json=data, timeout=10,verify=context)
        return response
    except Exception as error:
        print(error)
        return None


def update_blog_community(blog):
    """Update an InvenioRDM blog community."""
    try:
        context = ssl.create_default_context()
        if is_local():
            context = False
        url = f"{environ['QUART_INVENIORDM_API']}/api/communities/{blog.get('slug')}"
        headers = {"Authorization": f"Bearer {environ['QUART_INVENIORDM_TOKEN']}"}
        metadata = {
            "title": blog.get("title"),
            "type": {"id": "blog"},
            "website": blog.get("home_page_url"),
        }
        if blog.get("description", None):
            metadata["description"] = py_.truncate(
                blog.get("description", None), 250, omission="", separator=" "
            )
        custom_fields = compact({
            "rs:feed_url": blog.get("feed_url"),
            "rs:feed_format": blog.get("feed_format"),
            "rs:generator": blog.get("generator"),
            "rs:license": blog.get("license"),
            "rs:issn": blog.get("issn"),
            "rs:prefix": blog.get("prefix"),
            "rs:joined": get_date_from_unix_timestamp(blog.get("created_at", 0)),
            "rs:language": get_language(blog.get("language"), format="name"),
            "rs:category": FOS_MAPPINGS.get(blog.get("category"), None),
        })
        data = {
            "access": {
                "visibility": "public",
                "member_policy": "open",
                "record_policy": "open",
                "review_policy": "open",
            },
            "slug": blog.get("slug"),
            "metadata": metadata,
            "custom_fields": custom_fields,
        }
        response = httpx.put(url, headers=headers, json=data, timeout=10,verify=context)
        if response.status_code >= 400:
            print(response.json())
        return response
    except Exception as error:
        print(error)
        return None


def upload_blog_logo(blog):
    """Upload an InvenioRDM blog community logo."""
    if blog.get("favicon", None) is None:
        return None
    try:
        context = ssl.create_default_context()
        if is_local():
            context = False
        url = (
            f"{environ['QUART_INVENIORDM_API']}/api/communities/{blog.get('slug')}/logo"
        )
        headers = {
            "Content-Type": "application/octet-stream",
            "Authorization": f"Bearer {environ['QUART_INVENIORDM_TOKEN']}",
        }
        content = httpx.get(
            blog.get("favicon"), timeout=10, follow_redirects=True
        ).content
        response = httpx.put(url, headers=headers, content=content, timeout=10,verify=context)
        return response
    except Exception as error:
        print(error)
        return None


# def get_community(slug):
#     """Get InvenioRDM community by slug."""
#     try:
#         url = f"{environ['QUART_INVENIORDM_API']}/api/communities?q=slug:{slug}"
#         response = httpx.get(url, timeout=10)
#         print(response.json())
#         return response.json()
#         # result = response.json()
#         # if py_.get(result, "hits.total") != 1:
#         #     return result
#         # return py_.pick(
#         #     result,
#         #     [
#         #         "hits.hits[0].id",
#         #         "hits.hits[0].metadata.type.id",
#         #         "hits.hits[0].metadata.title",
#         #         "hits.hits[0].metadata.description",
#         #         "hits.hits[0].metadata.website",
#         #         "hits.hits[0].metadata.logo",
#         #     ],
#         # )
#     except Exception as error:
#         print(error)
#         return None


def feature_community(id):
    """Feature an InvenioRDM community by id."""
    try:
        context = ssl.create_default_context()
        if is_local():
            context = False
        url = f"{environ['QUART_INVENIORDM_API']}/api/communities/{id}/featured"
        headers = {"Authorization": f"Bearer {environ['QUART_INVENIORDM_TOKEN']}"}
        now = datetime.datetime.now().isoformat()
        data = {"start_date": now}
        response = httpx.post(url, headers=headers, json=data, timeout=10,verify=context)
        return response
    except Exception as error:
        print(error)
        return None
