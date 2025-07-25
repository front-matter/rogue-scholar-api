"""Posts module."""

from os import environ, path
from typing import Optional
from furl import furl
import httpx
import json as JSON
import yaml
import asyncio
import re
import pydash as py_
import nh3
import html
import xmltodict
import time
import traceback
from urllib.parse import unquote
from commonmeta import (
    Metadata,
    validate_doi,
    normalize_doi,
    validate_prefix,
    normalize_ror,
    presence,
)
from commonmeta.writers.inveniordm_writer import push_inveniordm

# from urllib.parse import urljoin
from commonmeta.date_utils import get_datetime_from_time
from commonmeta.doi_utils import is_rogue_scholar_doi
from math import ceil, floor
from Levenshtein import ratio
from sentry_sdk import capture_exception

from api.utils import (
    unix_timestamp,
    normalize_tag,
    get_date,
    normalize_url,
    get_src_url,
    get_soup,
    detect_language,
    normalize_author,
    extract_atom_authors,
    wrap,
    compact,
    fix_xml,
    write_html,
    validate_uuid,
    format_reference,
    format_json_reference,
    format_list_reference,
    format_citeproc_reference,
    convert_to_commonmeta,
    EXCLUDED_TAGS,
)
from api.supabase_client import (
    supabase_admin_client as supabase_admin,
    supabase_client as supabase,
    postsWithContentSelect,
    postsWithCitationsSelect,
)


async def extract_all_posts(
    page: int = 1, update_all: bool = False, validate_all: bool = False
):
    """Extract all posts."""

    blogs = (
        supabase.table("blogs")
        .select("slug")
        .in_("status", ["active", "expired"])
        .order("slug", desc=False)
        .execute()
    )
    tasks = []
    for blog in blogs.data:
        task = extract_all_posts_by_blog(blog["slug"], page, update_all, validate_all)
        tasks.append(task)

    raw_results = await asyncio.gather(*tasks)

    # flatten list of lists
    results = []
    for result in raw_results:
        if result:
            results.append(result[0])

    return results


async def update_all_posts(page: int = 1, validate_all: bool = False):
    """Update all posts."""

    blogs = (
        supabase.table("blogs")
        .select("slug")
        .in_("status", ["active", "expired", "archived", "pending"])
        .not_.is_("prefix", "null")
        .order("title", desc=False)
        .execute()
    )
    tasks = []
    for blog in blogs.data:
        task = update_all_posts_by_blog(blog["slug"], page, validate_all)
        tasks.append(task)

    raw_results = await asyncio.gather(*tasks)

    # flatten list of lists
    results = []
    for result in raw_results:
        if result:
            results.append(result[0])

    return results


async def update_all_cited_posts(page: int = 1, validate_all: bool = False):
    """Update all cited posts."""

    response = (
        supabase.table("posts")
        .select("*, citations: citations!inner(*)", count="exact", head=True)
        .execute()
    )
    total = response.count
    total_pages = ceil(total / 50)
    page = min(page, total_pages)
    start_page = (page - 1) * total_pages if page > 0 else 0
    end_page = (page - 1) * total_pages + total_pages if page > 0 else total_pages
    validate_all = True

    response = (
        supabase.table("posts")
        .select("*, blog: blogs!inner(*), citations: citations!inner(*)", count="exact")
        .order("updated_at", desc=False)
        .range(start_page, end_page)
        .execute()
    )
    tasks = []
    print(f"Updating cited posts from page {page} of {total_pages}.")
    for post in response.data:
        print("Updating cited post", post["doi"])
        blog = post.get("blog", None)
        task = update_rogue_scholar_post(post, blog, validate_all)
        tasks.append(task)

    cited_posts = await asyncio.gather(*tasks)
    return [upsert_single_post(i) for i in cited_posts]


async def update_all_flagged_posts(page: int = 1):
    """Update all flagged posts."""

    start_page = (page - 1) * 50 if page > 0 else 0
    end_page = (page - 1) * 50 + 50
    status = ["approved", "active", "archived", "expired"]
    validate_all = True

    response = (
        supabase.table("posts")
        .select(postsWithContentSelect, count="exact")
        .in_("status", status)
        .is_("content_html", "null")
        .order("published_at", desc=True)
        .range(start_page, end_page)
        .execute()
    )
    tasks = []
    for post in response.data:
        blog = post.get("blog", None)
        task = update_rogue_scholar_post(post, blog, validate_all)
        tasks.append(task)

    flagged_posts = await asyncio.gather(*tasks)
    return [upsert_single_post(i) for i in flagged_posts]


async def extract_all_posts_by_blog(
    slug: str,
    page: int = 1,
    update_all: bool = False,
    validate_all: bool = False,
):
    """Extract all posts by blog."""

    try:
        response = (
            supabase.table("blogs")
            .select(
                "id, slug, feed_url, current_feed_url, home_page_url, archive_prefix, archive_host, archive_collection, archive_timestamps, feed_format, created_at, updated_at, registered_at, generator, generator_raw, language, category, favicon, title, description, category, status, user_id, authors, use_api, relative_url, filter, secure, doi_as_guid"
            )
            .eq("slug", slug)
            .maybe_single()
            .execute()
        )
        if not response:
            return []
        blog = response.data
        if not blog:
            return {}
        if page == 1 and blog.get("slug") not in ["chem_bla_ics"]:
            url = furl(blog.get("current_feed_url", None) or blog.get("feed_url", None))
        else:
            url = furl(blog.get("feed_url", None))
        generator = (
            blog.get("generator", "").split(" ")[0]
            if blog.get("generator", None)
            else None
        )

        # get timestamp of last updated post
        response = (
            supabase.table("posts")
            .select("updated_at")
            .eq("blog_slug", slug)
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        if not response.data:
            updated_at = 0
        else:
            updated_at = response.data[0].get("updated_at", 0)

        # handle automatic pagination, based on number of posts already in the database
        if blog.get("slug", None) == "oan" and page == 999:
            response = (
                supabase.table("posts")
                .select("*", count="exact", head=True)
                .eq("blog_slug", slug)
                .execute()
            )
            total = response.count
            page = floor(total / 50)
        start_page = (page - 1) * 50 if page > 0 else 0
        end_page = (page - 1) * 50 + 50 if page > 0 else 50
        per_page = 50

        # handle pagination depending on blogging platform and whether we use their API
        match generator:
            case "WordPress":
                if blog.get("use_api", False):
                    url = furl(blog.get("home_page_url", None))
                    params = {
                        "rest_route": "/wp/v2/posts",
                        "page": page,
                        "per_page": per_page,
                        "_embed": 1,
                    }
                    if blog.get("filter", None):
                        filters = blog.get("filter", "").split(",")
                        categories = []
                        categories_exclude = []
                        tags = []
                        tags_exclude = []
                        for fi in filters:
                            f = fi.split(":")
                            if len(f) == 2 and f[0] == "category":
                                if int(f[1]) < 0:
                                    # exclude category if prefixed with minus sign
                                    categories_exclude.append(f[1][1:])
                                else:
                                    # otherwise include category
                                    categories.append(f[1])
                            elif len(f) == 2 and f[0] == "tag":
                                if int(f[1]) < 0:
                                    # exclude tag if prefixed with minus sign
                                    tags_exclude.append(f[1][1:])
                                else:
                                    # otherwise include tag
                                    tags.append(f[1])
                        if len(categories) > 0:
                            params["categories"] = ",".join(categories)
                        if len(categories_exclude) > 0:
                            params["categories_exclude"] = ",".join(categories_exclude)
                        if len(tags) > 0:
                            params["tags"] = ",".join(tags)
                        if len(tags_exclude) > 0:
                            params["tags_exclude"] = ",".join(tags_exclude)
                else:
                    params = {"paged": page}
            case "WordPress.com":
                if blog.get("use_api", False):
                    site = furl(blog.get("home_page_url", None)).host
                    url = url.set(
                        host="public-api.wordpress.com",
                        scheme="https" if blog.get("secure", True) else "http",
                        path="/rest/v1.1/sites/" + site + "/posts/",
                    )
                    params = {"page": page, "number": per_page}
                else:
                    params = {"paged": page}
            case "Ghost":
                if blog.get("use_api", False):
                    host = environ[f"QUART_{blog.get('slug').upper()}_GHOST_API_HOST"]
                    key = environ[f"QUART_{blog.get('slug').upper()}_GHOST_API_KEY"]
                    url = url.set(host=host, path="/ghost/api/content/posts/")
                    params = {
                        "page": page,
                        "limit": per_page,
                        "filter": blog.get("filter", None) or "visibility:public",
                        "include": "tags,authors",
                        "key": key,
                    }
                else:
                    params = {}
            case "Blogger":
                params = {"start-index": start_page + 1, "max-results": per_page}
            case "Substack":
                url = url.set(path="/api/v1/posts/")
                params = {"sort": "new", "offset": start_page, "limit": per_page}
            case "Squarespace":
                params = compact({"format": "json"})
            case _:
                params = url.args if url.args and url.args["type"] else {}
        feed_url = url.set(params).url
        print(f"Extracting posts from {blog['slug']} at {feed_url}.")
        blog_with_posts = {}

        # use pagination of results only for non-API blogs
        if params:
            start_page = 0
            end_page = per_page

        if generator == "Substack":
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.get(
                        feed_url, timeout=10.0, follow_redirects=True
                    )
                    response.raise_for_status()
                    posts = response.json()
                    # only include posts that have been modified since last update
                    if not update_all:
                        posts = filter_updated_posts(posts, updated_at, key="post_date")
                except httpx.HTTPStatusError:
                    print(f"HTTP status error for feed {feed_url}.")
                    posts = []
                except httpx.TransportError:
                    print(f"Transport error for feed {feed_url}.")
                    posts = []
                except httpx.HTTPError as e:
                    capture_exception(e)
                    posts = []
                extract_posts = [
                    extract_substack_post(x, blog, validate_all) for x in posts
                ]
            blog_with_posts["entries"] = await asyncio.gather(*extract_posts)
        elif generator == "WordPress" and blog["use_api"]:
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.get(
                        feed_url, timeout=30.0, follow_redirects=True
                    )
                    response.raise_for_status()
                    # filter out error messages that are not valid json
                    json_start = response.text.find("[{")
                    response = response.text[json_start:]
                    posts = JSON.loads(response)
                    if not update_all:
                        posts = filter_updated_posts(
                            posts, updated_at, key="modified_gmt"
                        )
                except httpx.HTTPStatusError:
                    print(f"HTTP status error for feed {feed_url}.")
                    posts = []
                except httpx.TransportError:
                    print(f"Transport error for feed {feed_url}.")
                    posts = []
                except httpx.HTTPError as e:
                    capture_exception(e)
                    posts = []
                extract_posts = [
                    extract_wordpress_post(x, blog, validate_all) for x in posts
                ]
            blog_with_posts["entries"] = await asyncio.gather(*extract_posts)
        elif generator == "WordPress.com" and blog["use_api"]:
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.get(
                        feed_url, timeout=10.0, follow_redirects=True
                    )
                    response.raise_for_status()
                    json = response.json()
                    posts = json.get("posts", [])
                    if not update_all:
                        posts = filter_updated_posts(posts, updated_at, key="modified")
                except httpx.HTTPStatusError:
                    print(f"HTTP status error for feed {feed_url}.")
                    posts = []
                except httpx.TransportError:
                    print(f"Transport error for feed {feed_url}.")
                    posts = []
                except httpx.HTTPError as e:
                    capture_exception(e)
                    posts = []
                extract_posts = [
                    extract_wordpresscom_post(x, blog, validate_all) for x in posts
                ]
            blog_with_posts["entries"] = await asyncio.gather(*extract_posts)
        elif generator == "Ghost" and blog["use_api"]:
            headers = {"Accept-Version": "v5.0"}
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.get(feed_url, timeout=10.0, headers=headers)
                    response.raise_for_status()
                    json = response.json()
                    posts = json.get("posts", [])
                    if not update_all:
                        posts = filter_updated_posts(
                            posts, updated_at, key="updated_at"
                        )
                except httpx.HTTPStatusError:
                    print(f"HTTP status error for feed {feed_url}.")
                    posts = []
                except httpx.TransportError:
                    print(f"Transport error for feed {feed_url}.")
                    posts = []
                except httpx.HTTPError as e:
                    capture_exception(e)
                    posts = []
                extract_posts = [
                    extract_ghost_post(x, blog, validate_all) for x in posts
                ]
            blog_with_posts["entries"] = await asyncio.gather(*extract_posts)
        elif generator == "Squarespace":
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.get(
                        feed_url, timeout=10.0, follow_redirects=True
                    )
                    response.raise_for_status()
                    json = response.json()
                    posts = json.get("items", [])
                    # only include posts that have been modified since last update
                    if not update_all:
                        posts = filter_updated_posts(posts, updated_at, key="pubDate")
                except httpx.HTTPStatusError:
                    print(f"HTTP status error for feed {feed_url}.")
                    posts = []
                except httpx.TransportError:
                    print(f"Transport error for feed {feed_url}.")
                    posts = []
                except httpx.HTTPError as e:
                    capture_exception(e)
                    posts = []
                extract_posts = [
                    extract_squarespace_post(x, blog, validate_all) for x in posts
                ]
            blog_with_posts["entries"] = await asyncio.gather(*extract_posts)
        elif blog["feed_format"] == "application/feed+json":
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.get(
                        feed_url, timeout=10.0, follow_redirects=True
                    )
                    response.raise_for_status()
                    json = response.json()
                    posts = json.get("items", [])
                    if not update_all:
                        posts = filter_updated_posts(
                            posts, updated_at, key="date_modified"
                        )
                    if blog.get("filter", None):
                        posts = filter_posts(posts, blog, key="tags")
                    if blog.get("doi_as_guid", False):
                        posts = filter_posts_by_guid(posts, blog, key="id")
                    posts = posts[start_page:end_page]
                except httpx.HTTPStatusError:
                    print(f"HTTP status error for feed {feed_url}.")
                    posts = []
                except httpx.TransportError:
                    print(f"Transport error for feed {feed_url}.")
                    posts = []
                except JSON.decoder.JSONDecodeError:
                    print(f"JSON decode error for feed {feed_url}.")
                    posts = []
                except httpx.HTTPError as e:
                    capture_exception(e)
                    posts = []
                extract_posts = [
                    extract_json_feed_post(x, blog, validate_all) for x in posts
                ]
            blog_with_posts["entries"] = await asyncio.gather(*extract_posts)
        elif blog["feed_format"] == "application/atom+xml":
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.get(
                        feed_url, timeout=30.0, follow_redirects=True
                    )
                    response.raise_for_status()
                    # fix malformed xml
                    xml = fix_xml(response.read())
                    json = xmltodict.parse(
                        xml, dict_constructor=dict, force_list={"entry"}
                    )
                    posts = py_.get(json, "feed.entry", [])
                    if not update_all:
                        posts = filter_updated_posts(posts, updated_at, key="published")
                    if blog.get("filter", None):
                        posts = filter_posts(posts, blog, key="category")
                    posts = posts[start_page:end_page]
                except httpx.HTTPStatusError:
                    print(f"HTTP status error for feed {feed_url}.")
                    posts = []
                except httpx.TransportError:
                    print(f"Transport error for feed {feed_url}.")
                    posts = []
                except httpx.HTTPError as e:
                    capture_exception(e)
                    posts = []
            extract_posts = [extract_atom_post(x, blog, validate_all) for x in posts]
            blog_with_posts["entries"] = await asyncio.gather(*extract_posts)
        elif blog["feed_format"] == "application/rss+xml":
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.get(
                        feed_url, timeout=10.0, follow_redirects=True
                    )
                    response.raise_for_status()
                    # fix malformed xml
                    xml = fix_xml(response.read())
                    json = xmltodict.parse(
                        xml, dict_constructor=dict, force_list={"category", "item"}
                    )
                    posts = py_.get(json, "rss.channel.item", [])
                    if not update_all:
                        posts = filter_updated_posts(posts, updated_at, key="pubDate")
                    if blog.get("filter", None):
                        posts = filter_posts(posts, blog, key="category")
                    posts = posts[start_page:end_page]
                except httpx.HTTPStatusError:
                    print(f"HTTP status error for feed {feed_url}.")
                    posts = []
                except httpx.TransportError:
                    print(f"Transport error for feed {feed_url}.")
                    posts = []
                except httpx.HTTPError as e:
                    capture_exception(e)
                    posts = []
            extract_posts = [extract_rss_post(x, blog, validate_all) for x in posts]
            blog_with_posts["entries"] = await asyncio.gather(*extract_posts)
        else:
            blog_with_posts["entries"] = []
        if blog.get("status", None) not in ["pending", "active", "expired", "archived"]:
            return blog_with_posts["entries"]
        n = len(blog_with_posts["entries"])
        if n > 0:
            print(f"Extracting {n} posts from {blog['slug']} at {feed_url}.")
        return [upsert_single_post(i) for i in blog_with_posts["entries"]]
    except Exception as e:
        print(f"{e} error.")
        print(traceback.format_exc())
        return []


async def update_all_posts_by_blog(
    slug: str, page: int = 1, validate_all: bool = False
):
    """Update all posts by blog."""

    try:
        response = (
            supabase.table("blogs")
            .select(
                "id, slug, feed_url, current_feed_url, home_page_url, archive_prefix, archive_host, archive_collection, archive_timestamps, feed_format, created_at, updated_at, registered_at, mastodon, generator, generator_raw, language, category, favicon, title, description, category, status, user_id, authors, use_api, relative_url, filter, secure"
            )
            .eq("slug", slug)
            .maybe_single()
            .execute()
        )
        blog = response.data
        if not blog:
            return {}

        start_page = (page - 1) * 50 if page > 0 else 0
        end_page = (page - 1) * 50 + 50 if page > 0 else 50
        blog_with_posts = {}

        response = (
            supabase.table("posts")
            .select(postsWithContentSelect)
            .eq("blog_slug", blog["slug"])
            .order("published_at", desc=True)
            .range(start_page, end_page)
            .execute()
        )
        update_posts = [
            update_rogue_scholar_post(x, blog, validate_all) for x in response.data
        ]
        blog_with_posts["entries"] = await asyncio.gather(*update_posts)
        return [upsert_single_post(i) for i in blog_with_posts["entries"]]
    except TimeoutError:
        print(f"Timeout error in blog {blog['slug']}.")
        return []
    except Exception as e:
        print(f"{e} error in blog {blog['slug']}.")
        print(traceback.format_exc())
        return []


async def get_single_post(slug: str, suffix: Optional[str] = None):
    """Get single post."""
    try:
        if validate_uuid(slug):
            response = (
                supabase.table("posts")
                .select(postsWithContentSelect)
                .eq("id", slug)
                .maybe_single()
                .execute()
            )
        elif validate_prefix(slug) and suffix:
            doi = f"https://doi.org/{slug}/{suffix}"
            response = (
                supabase.table("posts")
                .select(postsWithContentSelect)
                .eq("doi", doi)
                .maybe_single()
                .execute()
            )
        else:
            return {"error": "An error occured."}, 400
        return response.data
    except Exception:
        print(traceback.format_exc())
        return {}


async def extract_single_post(
    slug: str,
    suffix: str,
    validate_all: bool = False,
):
    """Extract single post from blog. Support is still experimental, as there are
    many challenges, e.g. pagination."""

    try:
        guid = None
        if validate_uuid(slug):
            response = (
                supabase.table("posts")
                .select(postsWithCitationsSelect)
                .eq("id", slug)
                .maybe_single()
                .execute()
            )
            if not response:
                response = (
                    supabase.table("posts")
                    .select(postsWithContentSelect)
                    .eq("id", slug)
                    .maybe_single()
                    .execute()
                )
            guid = py_.get(response.data, "guid")
            post_url = py_.get(response.data, "url")
            blog = py_.get(response.data, "blog")
        elif validate_prefix(slug) and suffix:
            doi = f"https://doi.org/{slug}/{suffix}"
            response = (
                supabase.table("posts")
                .select(postsWithCitationsSelect)
                .eq("doi", doi)
                .maybe_single()
                .execute()
            )
            if not response:
                response = (
                    supabase.table("posts")
                    .select(postsWithContentSelect)
                    .eq("doi", doi)
                    .maybe_single()
                    .execute()
                )
            guid = py_.get(response.data, "guid")
            post_url = py_.get(response.data, "url")
            blog = py_.get(response.data, "blog")
        else:
            return {"error": "An error occured."}, 400

        generator = (
            blog.get("generator", "").split(" ")[0]
            if blog.get("generator", None)
            else None
        )

        # generate url depending on the platform and whether we use their API
        match generator:
            case "WordPress":
                if blog.get("use_api", False):
                    site = furl(blog.get("home_page_url", None)).host
                    id_ = furl(guid).args["p"]
                    f = furl()
                    f.host = site
                    f.scheme = "https" if blog.get("secure", True) else "http"
                    f.path = f"/wp-json/wp/v2/posts/{id_}"
                    f.args = {"_embed": 1}
                else:
                    f = furl(blog.get("feed_url", None))
            case "WordPress.com":
                if blog.get("use_api", False):
                    site = furl(blog.get("home_page_url", None)).host
                    id_ = furl(guid).args["p"]
                    f = furl()
                    f.host = "public-api.wordpress.com"
                    f.scheme = "https" if blog.get("secure", True) else "http"
                    f.path = f"/rest/v1.1/sites/{site}/posts/{id_}"
                else:
                    f = furl(blog.get("feed_url", None))
            case "Ghost":
                if blog.get("use_api", False):
                    host = environ[f"QUART_{blog.get('slug').upper()}_GHOST_API_HOST"]
                    key = environ[f"QUART_{blog.get('slug').upper()}_GHOST_API_KEY"]
                    path = furl(post_url).path.segments[-2]
                    f = furl()
                    f.host = host
                    f.scheme = "https"
                    f.path = f"/ghost/api/content/posts/slug/{path}/"
                    f.args = {
                        "include": "tags,authors",
                        "key": key,
                    }
                else:
                    f = furl(blog.get("feed_url", None))
            case "Substack":
                site = furl(blog.get("home_page_url", None)).host
                path = furl(post_url).path.segments[-1]
                f = furl()
                f.host = site
                f.scheme = "https"
                f.path = f"/api/v1/posts/{path}"
            # case "Squarespace":
            # params = compact({"format": "json"})
            case _:
                f = furl(blog.get("feed_url", None))
        feed_url = f.url
        print(f"Extracting post from {blog['slug']} at {feed_url}.")

        if generator == "Substack":
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.get(
                        feed_url, timeout=10.0, follow_redirects=True
                    )
                    response.raise_for_status()
                    post = response.json()
                except httpx.HTTPStatusError:
                    print(f"HTTP status error for feed {feed_url}.")
                    post = {}
                except httpx.TransportError:
                    print(f"Transport error for feed {feed_url}.")
                    post = {}
                except httpx.HTTPError as e:
                    capture_exception(e)
                    post = {}
                extract_posts = [await extract_substack_post(post, blog, validate_all)]
        elif generator == "WordPress" and blog["use_api"]:
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.get(
                        feed_url, timeout=30.0, follow_redirects=True
                    )
                    response.raise_for_status()
                    post = response.json()
                except httpx.HTTPStatusError:
                    print(f"HTTP status error for feed {feed_url}.")
                    post = {}
                except httpx.TransportError:
                    print(f"Transport error for feed {feed_url}.")
                    post = {}
                except httpx.HTTPError as e:
                    capture_exception(e)
                    post = {}
                extract_posts = [await extract_wordpress_post(post, blog, validate_all)]
        elif generator == "WordPress.com" and blog["use_api"]:
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.get(
                        feed_url, timeout=10.0, follow_redirects=True
                    )
                    response.raise_for_status()
                    post = response.json()
                except httpx.HTTPStatusError:
                    print(f"HTTP status error for feed {feed_url}.")
                    post = {}
                except httpx.TransportError:
                    print(f"Transport error for feed {feed_url}.")
                    post = {}
                except httpx.HTTPError as e:
                    capture_exception(e)
                    post = {}
                extract_posts = [
                    await extract_wordpresscom_post(post, blog, validate_all)
                ]
        elif generator == "Ghost" and blog["use_api"]:
            headers = {"Accept-Version": "v5.0"}
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.get(feed_url, timeout=10.0, headers=headers)
                    response.raise_for_status()
                    json = response.json()
                    posts = json.get("posts", [])
                except httpx.HTTPStatusError:
                    print(response.status_code)
                    print(f"HTTP status error for feed {feed_url}.")
                    posts = []
                except httpx.TransportError:
                    print(f"Transport error for feed {feed_url}.")
                    posts = []
                except httpx.HTTPError as e:
                    capture_exception(e)
                    posts = []
                extract_posts = [
                    await extract_ghost_post(x, blog, validate_all) for x in posts
                ]
        elif blog.get("feed_format", None) == "application/feed+json":
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.get(
                        feed_url, timeout=10.0, follow_redirects=True
                    )
                    response.raise_for_status()
                    json = response.json()
                    posts = json.get("items", [])
                    post = find_post_by_guid(posts, guid, "id")
                except httpx.HTTPStatusError:
                    print(f"HTTP status error for feed {feed_url}.")
                    post = {}
                except httpx.TransportError:
                    print(f"Transport error for feed {feed_url}.")
                    post = {}
                except httpx.HTTPError as e:
                    capture_exception(e)
                    post = {}
                extract_posts = [await extract_json_feed_post(post, blog, validate_all)]
        elif blog.get("feed_format", None) == "application/atom+xml":
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.get(
                        feed_url, timeout=30.0, follow_redirects=True
                    )
                    response.raise_for_status()
                    # fix malformed xml
                    xml = fix_xml(response.read())
                    json = xmltodict.parse(
                        xml, dict_constructor=dict, force_list={"entry"}
                    )
                    posts = py_.get(json, "feed.entry", [])
                    post = find_post_by_guid(posts, guid, "id")
                except httpx.HTTPStatusError:
                    print(f"HTTP status error for feed {feed_url}.")
                    post = {}
                except httpx.TransportError:
                    print(f"Transport error for feed {feed_url}.")
                    post = {}
                except httpx.HTTPError as e:
                    capture_exception(e)
                    post = {}
                extract_posts = [await extract_atom_post(post, blog, validate_all)]
        elif blog["feed_format"] == "application/rss+xml":
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.get(
                        feed_url, timeout=10.0, follow_redirects=True
                    )
                    response.raise_for_status()
                    # fix malformed xml
                    xml = fix_xml(response.read())
                    json = xmltodict.parse(
                        xml, dict_constructor=dict, force_list={"category", "item"}
                    )
                    posts = py_.get(json, "rss.channel.item", [])
                    post = find_post_by_guid(posts, guid, "guid")
                except httpx.HTTPStatusError:
                    print(f"HTTP status error for feed {feed_url}.")
                    post = {}
                except httpx.TransportError:
                    print(f"Transport error for feed {feed_url}.")
                    post = {}
                except httpx.HTTPError as e:
                    capture_exception(e)
                    post = {}
                extract_posts = [await extract_rss_post(post, blog, validate_all)]
        return [upsert_single_post(i) for i in extract_posts]
    except Exception:
        print(traceback.format_exc())
        return {}


async def update_single_post(
    slug: str, suffix: Optional[str] = None, validate_all: bool = False
):
    """Update single post"""

    try:
        if validate_uuid(slug):
            response = (
                supabase.table("posts")
                .select(postsWithCitationsSelect)
                .eq("id", slug)
                .maybe_single()
                .execute()
            )
            if not response:
                response = (
                    supabase.table("posts")
                    .select(postsWithContentSelect)
                    .eq("id", slug)
                    .maybe_single()
                    .execute()
                )
        elif validate_prefix(slug) and suffix:
            doi = f"https://doi.org/{slug}/{suffix}"
            response = (
                supabase.table("posts")
                .select(postsWithCitationsSelect)
                .eq("doi", doi)
                .maybe_single()
                .execute()
            )
            if not response:
                response = (
                    supabase.table("posts")
                    .select(postsWithContentSelect)
                    .eq("doi", doi)
                    .maybe_single()
                    .execute()
                )
        else:
            return {"error": "An error occured."}, 400
        if not response or not response.data:
            return {"error": "An error occured."}, 400
        blog = py_.get(response.data, "blog")
        if not blog:
            return {"error": "Blog not found."}, 404
        post = py_.omit(response.data, "blog")
        updated_post = await update_rogue_scholar_post(post, blog, validate_all)
        response = upsert_single_post(updated_post)
        return response
    except Exception:
        print(traceback.format_exc())
        return {}


async def extract_wordpress_post(post, blog, validate_all: bool = False):
    """Extract WordPress post from REST API."""

    try:

        def format_author(author, published_at):
            """Format author. Optionally lookup real name from username,
            and ORCID from name. Ideally this is done in the Wordpress
            user settings."""

            return normalize_author(
                author.get("name", None), published_at, author.get("url", None)
            )

        published_at = unix_timestamp(post.get("date_gmt", None))
        authors_ = wrap(py_.get(post, "_embedded.author", None))
        title = py_.get(post, "title.rendered", "")

        # check for author name in title
        author = None
        title_parts = title.split(" by ")
        if (
            len(title_parts) > 1
            and authors_
            and py_.get(authors_, "0.name", None) in ["CSTonline"]
        ):
            title = title_parts[0]
            author = title_parts[1]
        elif (
            len(title_parts) > 1
            and authors_
            and py_.get(authors_, "0.name", None) in ["The BJPS"]
        ):
            title = title_parts[0].replace("// Reviewed", "").strip()
            author = title_parts[1]
        if author:
            authors_ = [{"name": author}]

        # use default author for blog if no post author found
        if len(authors_) == 0 or authors_[0].get("name", None) is None:
            authors_ = wrap(blog.get("authors", None))
        authors = [format_author(i, published_at) for i in authors_]
        content_html = py_.get(post, "content.rendered", "")
        summary = get_summary(content_html)
        abstract = get_summary(py_.get(post, "excerpt.rendered", ""))
        abstract = get_abstract(summary, abstract)
        reference = await get_references(content_html, validate_all)
        relationships = get_relationships(content_html)
        funding_references = wrap(blog.get("funding", None))
        url = normalize_url(post.get("link", None), secure=blog.get("secure", True))
        archive_url = get_archive_url(blog, url, published_at)
        images = get_images(content_html, url, blog["home_page_url"])
        image = (
            py_.get(post, "_embedded.wp:featuredmedia[0].source_url", None)
            or py_.get(post, "yoast_head_json.og_image[0].url", None)
            or post.get("jetpack_featured_media_url", None)
        )

        # optionally remove terms (categories and tags) used to filter posts
        if blog.get("filter", None):
            filters = blog.get("filter", "").split(",")
            terms = []
            for fi in filters:
                f = fi.split(":")
                if int(f[1]) < 0:
                    # exclude term if prefixed with minus sign
                    terms.append(f[1][1:])
            categories = [
                normalize_tag(i.get("name", None))
                for i in wrap(py_.get(post, "_embedded.wp:term.0", None))
                if i.get("id", None) not in terms
                and i.get("name", "").split(":")[0] not in EXCLUDED_TAGS
            ]
        else:
            categories = [
                normalize_tag(i.get("name", None))
                for i in wrap(py_.get(post, "_embedded.wp:term.0", None))
                if i.get("name", "").split(":")[0] not in EXCLUDED_TAGS
            ]

        # optionally remove tag that is used to filter posts
        if blog.get("filter", None) and blog.get("filter", "").startswith("tag"):
            tag = blog.get("filter", "").split(":")[1]
            tags = [
                normalize_tag(i.get("name", None))
                for i in wrap(py_.get(post, "_embedded.wp:term.1", None))
                if i.get("id", None) != int(tag)
                and i.get("name", "").split(":")[0] not in EXCLUDED_TAGS
            ]
        tags = [
            normalize_tag(i.get("name", None))
            for i in wrap(py_.get(post, "_embedded.wp:term.1", None))
            if i.get("name", "").split(":")[0] not in EXCLUDED_TAGS
        ]
        terms = categories + tags
        terms = py_.uniq(terms)[:5]

        return {
            "authors": authors,
            "blog_name": blog.get("title", None),
            "blog_slug": blog.get("slug", None),
            "content_html": content_html,
            "summary": summary,
            "abstract": abstract,
            "published_at": published_at,
            "updated_at": unix_timestamp(post.get("modified_gmt", None)),
            "image": image,
            "images": images,
            "language": detect_language(content_html) or blog.get("language", "en"),
            "category": blog.get("category", None),
            "reference": reference,
            "relationships": relationships,
            "funding_references": presence(funding_references),
            "tags": terms,
            "title": title,
            "url": url,
            "archive_url": archive_url,
            "guid": py_.get(post, "guid.rendered", None),
            "status": blog.get("status", "active"),
        }
    except Exception:
        print(blog.get("slug", None), traceback.format_exc())
        return {}


async def extract_wordpresscom_post(post, blog, validate_all: bool = False):
    """Extract WordPress.com post from REST API."""
    try:

        def format_author(author, published_at):
            """Format author. Optionally lookup real name from username,
            and ORCID from name. Ideally this is done in the Wordpress
            user settings."""

            return normalize_author(
                author.get("name", None), published_at, author.get("URL", None)
            )

        published_at = unix_timestamp(post.get("date", None))
        authors = [
            format_author(i, published_at) for i in wrap(post.get("author", None))
        ]
        content_html = post.get("content", "")
        summary = get_summary(post.get("content", ""))
        abstract = get_summary(post.get("excerpt", None))
        abstract = get_abstract(summary, abstract)
        reference = await get_references(content_html, validate_all)
        relationships = get_relationships(content_html)
        funding_references = wrap(blog.get("funding", None))
        url = normalize_url(post.get("URL", None), secure=blog.get("secure", True))
        archive_url = get_archive_url(blog, url, published_at)
        images = get_images(content_html, url, blog.get("home_page_url", None))
        image = post.get("featured_image", None)
        tags = [
            normalize_tag(i)
            for i in post.get("categories", None).keys()
            if i.split(":")[0] not in EXCLUDED_TAGS
        ][:5]

        return {
            "authors": authors,
            "blog_name": blog.get("title", None),
            "blog_slug": blog.get("slug", None),
            "content_html": content_html,
            "summary": summary,
            "abstract": abstract,
            "published_at": published_at,
            "updated_at": unix_timestamp(post.get("modified", None)),
            "image": image,
            "images": images,
            "language": detect_language(content_html) or blog.get("language", "en"),
            "category": blog.get("category", None),
            "reference": reference,
            "relationships": relationships,
            "funding_references": presence(funding_references),
            "tags": tags,
            "title": get_title(post.get("title", None)),
            "url": url,
            "archive_url": archive_url,
            "guid": post.get("guid", None),
            "status": blog.get("status", "active"),
        }
    except Exception:
        print(blog.get("slug", None), traceback.format_exc())
        return {}


async def extract_ghost_post(post, blog, validate_all: bool = False):
    """Extract Ghost post from REST API."""

    try:

        def format_author(author, published_at):
            """Format author."""
            return normalize_author(
                author.get("name", None), published_at, author.get("website", None)
            )

        published_at = unix_timestamp(post.get("published_at", None))
        authors = [
            format_author(i, published_at) for i in wrap(post.get("authors", None))
        ]
        content_html = post.get("html", "")

        # don't use excerpt as summary, because it's not html
        summary = get_summary(content_html)
        abstract = get_summary(post.get("excerpt", ""))
        abstract = get_abstract(summary, abstract)
        reference = await get_references(content_html, validate_all)
        relationships = get_relationships(content_html)
        funding_references = wrap(blog.get("funding", None))
        url = normalize_url(post.get("url", None), secure=blog.get("secure", True))
        archive_url = get_archive_url(blog, url, published_at)
        guid = post.get("canonical_url", None)
        if not guid:
            guid = post.get("id", None)
        images = get_images(content_html, url, blog.get("home_page_url", None))
        image = post.get("feature_image", None)
        tags = [
            normalize_tag(i.get("name", None))
            for i in post.get("tags", None)
            if i.get("name", "").split(":")[0] not in EXCLUDED_TAGS
        ][:5]

        return {
            "authors": authors,
            "blog_name": blog.get("title", None),
            "blog_slug": blog.get("slug", None),
            "content_html": content_html,
            "summary": summary,
            "abstract": abstract,
            "published_at": published_at,
            "updated_at": unix_timestamp(post.get("updated_at", None)),
            "image": image,
            "images": images,
            "language": detect_language(content_html) or blog.get("language", "en"),
            "category": blog.get("category", None),
            "reference": reference,
            "relationships": relationships,
            "funding_references": presence(funding_references),
            "tags": tags,
            "title": get_title(post.get("title", None)),
            "url": url,
            "archive_url": archive_url,
            "guid": guid,
            "status": blog.get("status", "active"),
        }
    except Exception:
        print(blog.get("slug", None), traceback.format_exc())
        return {}


async def extract_substack_post(post, blog, validate_all: bool = False):
    """Extract Substack post from REST API."""

    try:

        def format_author(author, published_at):
            """Format author."""
            return normalize_author(author.get("name", None), published_at)

        published_at = unix_timestamp(post.get("post_date", None))
        authors = [
            format_author(i, published_at)
            for i in wrap(post.get("publishedBylines", None))
        ]
        if len(authors) == 0:
            authors = wrap(blog.get("authors", None))
        content_html = post.get("body_html", "")
        summary = get_summary(post.get("description", None))
        abstract = get_summary(content_html)
        abstract = get_abstract(summary, abstract)
        reference = await get_references(content_html, validate_all)
        relationships = get_relationships(content_html)
        funding_references = wrap(blog.get("funding", None))
        url = normalize_url(
            post.get("canonical_url", None), secure=blog.get("secure", True)
        )
        archive_url = get_archive_url(blog, url, published_at)
        images = get_images(content_html, url, blog.get("home_page_url", None))
        image = post.get("cover_image", None)
        tags = [
            normalize_tag(i.get("name"))
            for i in wrap(post.get("postTags", None))
            if i.get("name", "").split(":")[0] not in EXCLUDED_TAGS
        ][:5]

        return {
            "authors": authors,
            "blog_name": blog.get("title", None),
            "blog_slug": blog.get("slug", None),
            "content_html": content_html,
            "summary": summary,
            "abstract": abstract,
            "published_at": published_at,
            "updated_at": published_at,
            "image": image,
            "images": images,
            "language": detect_language(content_html) or blog.get("language", "en"),
            "category": blog.get("category", None),
            "reference": reference,
            "relationships": relationships,
            "funding_references": presence(funding_references),
            "tags": tags,
            "title": get_title(post.get("title", None)),
            "url": url,
            "archive_url": archive_url,
            "guid": post.get("id", None),
            "status": blog.get("status", "active"),
        }
    except Exception:
        print(blog.get("slug", None), traceback.format_exc())
        return {}


async def extract_squarespace_post(post, blog, validate_all: bool = False):
    """Extract Squarespace post from REST API."""

    try:

        def format_author(author, published_at):
            """Format author."""

            return normalize_author(author.get("displayName", None), published_at)

        published_at = int(post.get("publishOn", 1) / 1000)
        updated_at = int(post.get("updatedOn", 1) / 1000)
        authors = [
            format_author(i, published_at) for i in wrap(post.get("author", None))
        ]
        content_html = post.get("body", "")
        summary = get_summary(content_html)
        abstract = get_summary(post.get("excerpt", ""))
        if abstract is not None:
            abstract = get_abstract(summary, abstract)

        reference = await get_references(content_html, validate_all)
        relationships = get_relationships(content_html)
        funding_references = wrap(blog.get("funding", None))
        url = normalize_url(
            f"{blog.get('home_page_url', '')}/{post.get('urlId', '')}",
            secure=blog.get("secure", True),
        )
        archive_url = get_archive_url(blog, url, published_at)
        images = get_images(content_html, url, blog.get("home_page_url", None))
        image = post.get("assetUrl", None)
        tags = [
            normalize_tag(i)
            for i in wrap(post.get("categories", None))
            if i.split(":")[0] not in EXCLUDED_TAGS
        ][:5]

        return {
            "authors": authors,
            "blog_name": blog.get("title", None),
            "blog_slug": blog.get("slug", None),
            "content_html": content_html,
            "summary": summary,
            "abstract": abstract,
            "published_at": published_at,
            "updated_at": updated_at,
            "image": image,
            "images": images,
            "language": detect_language(content_html) or blog.get("language", "en"),
            "category": blog.get("category", None),
            "reference": reference,
            "relationships": relationships,
            "funding_references": presence(funding_references),
            "tags": tags,
            "title": get_title(post.get("title", None)),
            "url": url,
            "archive_url": archive_url,
            "guid": post.get("id", None),
            "status": blog.get("status", "active"),
        }
    except Exception:
        print(blog.get("slug", None), traceback.format_exc())
        return {}


async def extract_json_feed_post(post, blog, validate_all: bool = False):
    """Extract JSON Feed post."""

    try:

        def format_author(author, published_at):
            """Format author."""
            return normalize_author(
                author.get("name", None), published_at, author.get("url", None)
            )

        published_at = unix_timestamp(post.get("date_published", None))

        # use default authors for blog if no post authors found
        authors_ = wrap(post.get("authors", None))
        if len(authors_) == 0:
            authors_ = wrap(blog.get("authors", None))
        authors = [format_author(i, published_at) for i in authors_]
        content_html = post.get("content_html", "")
        url = normalize_url(post.get("url", None), secure=blog.get("secure", True))
        content_html = absolute_urls(content_html, url, blog.get("home_page_url", None))
        summary = get_summary(content_html)
        abstract = post.get("summary", None)
        abstract = get_abstract(summary, abstract)
        reference = await get_jsonfeed_references(
            post.get("_references", []), validate_all
        )
        if len(reference) == 0:
            reference = await get_references(content_html, validate_all)
        relationships = get_relationships(content_html)
        funding_references = (
            wrap(blog.get("funding", None))
            + await get_funding(content_html)
            + await get_funding_references(post.get("_funding", None))
        )
        archive_url = get_archive_url(blog, url, published_at)
        base_url = url
        if blog.get("relative_url", None) == "blog":
            base_url = blog.get("home_page_url", None)
        images = get_images(content_html, base_url, blog.get("home_page_url", None))
        image = py_.get(post, "media:thumbnail.@url", None)
        tags = [
            normalize_tag(i)
            for i in wrap(post.get("tags", None))
            if i.split(":")[0] not in EXCLUDED_TAGS
        ][:5]

        return {
            "authors": authors,
            "blog_name": blog.get("title", None),
            "blog_slug": blog.get("slug", None),
            "content_html": content_html,
            "summary": summary,
            "abstract": abstract,
            "published_at": published_at,
            "updated_at": unix_timestamp(post.get("date_modified", None)),
            "image": image,
            "images": images,
            "language": detect_language(content_html) or blog.get("language", "en"),
            "category": blog.get("category", None),
            "reference": reference,
            "relationships": relationships,
            "funding_references": presence(funding_references),
            "tags": tags,
            "title": get_title(post.get("title", None)),
            "url": url,
            "archive_url": archive_url,
            "guid": post.get("id", None),
            "status": blog.get("status", "active"),
        }
    except Exception:
        print(blog.get("slug", None), traceback.format_exc())
        return {}


async def extract_atom_post(post, blog, validate_all: bool = False):
    """Extract Atom post."""

    try:

        def format_author(author, published_at):
            """Format author."""
            return normalize_author(
                author.get("name", None), published_at, author.get("uri", None)
            )

        published_at = get_date(post.get("published", None))
        published_at = unix_timestamp(published_at)
        updated_at = get_date(post.get("updated", None))
        updated_at = unix_timestamp(updated_at)
        # if updated date is missing or earlier than published date, use published date
        if published_at > updated_at:
            updated_at = published_at

        # if published date is missing, use updated date
        if published_at == 0:
            published_at = updated_at

        # use default authors for blog if no post authors found
        authors_ = wrap(post.get("author", None))
        if (
            len(authors_) == 0
            or authors_[0].get("name", None) is None
            or authors_[0].get("name", None) == "Unknown"
            or blog.get("slug") in ["bibliomagician"]
        ):
            authors_ = wrap(blog.get("authors", None))
        # workaround if multiple authors are present in single author attribute
        elif len(authors_) == 1:
            authors_ = extract_atom_authors(authors_[0])
        authors = [format_author(i, published_at) for i in authors_]

        # workaround, as content should be encodes as CDATA block
        content_html = html.unescape(py_.get(post, "content.#text", ""))
        if content_html == "":
            content_html = html.unescape(py_.get(post, "content.div.#text", ""))

        def get_url(links):
            """Get url."""
            return normalize_url(
                next(
                    (
                        link["@href"]
                        for link in wrap(links)
                        if link["@rel"] == "alternate"
                    ),
                    None,
                ),
                secure=blog.get("secure", True),
            )

        url = normalize_url(py_.get(post, "link.@href", None))
        if not isinstance(url, str):
            url = get_url(post.get("link", None))
        if blog.get("slug", None) == "oan":
            url = normalize_blogger_url(url)
        archive_url = get_archive_url(blog, url, published_at)
        base_url = url
        if blog.get("relative_url", None) == "blog":
            base_url = blog.get("home_page_url", None)
        content_html = absolute_urls(content_html, url, blog.get("home_page_url", None))
        title = get_title(py_.get(post, "title.#text", None)) or get_title(
            post.get("title", None)
        )
        summary = get_summary(content_html)
        abstract = py_.get(post, "summary.#text", None)
        abstract = get_abstract(summary, abstract)
        reference = await get_references(content_html, validate_all)
        relationships = get_relationships(content_html)
        funding_references = wrap(blog.get("funding", None))
        images = get_images(content_html, base_url, blog.get("home_page_url", None))
        image = py_.get(post, "media:thumbnail.@url", None)
        # workaround for eve blog
        if image is not None:
            f = furl(image)
            if f.host == "eve.gd":
                image = unquote(image)
                if f.path.segments[0] != "images":
                    image = f.set(path="/images/" + f.path.segments[0]).url
        tags = [
            normalize_tag(i.get("@term", None))
            for i in wrap(post.get("category", None))
            if i.get("@term", "").split(":")[0] not in EXCLUDED_TAGS
        ][:5]

        return {
            "authors": authors,
            "blog_name": blog.get("title", None),
            "blog_slug": blog.get("slug", None),
            "content_html": content_html,
            "summary": summary,
            "abstract": abstract,
            "published_at": published_at,
            "updated_at": updated_at,
            "image": image,
            "images": images,
            "language": detect_language(content_html) or blog.get("language", "en"),
            "category": blog.get("category", None),
            "reference": reference,
            "relationships": relationships,
            "funding_references": presence(funding_references),
            "tags": tags,
            "title": title,
            "url": url,
            "archive_url": archive_url,
            "guid": post.get("id", None),
            "status": blog.get("status", "active"),
        }
    except Exception:
        print(blog.get("slug", None), traceback.format_exc())
        return {}


async def extract_rss_post(post, blog, validate_all: bool = False):
    """Extract RSS post."""

    try:

        def format_author(author, published_at):
            """Format author."""
            return normalize_author(
                author.get("name", None), published_at, author.get("url", None)
            )

        published_at = get_date(post.get("pubDate", None))
        published_at = unix_timestamp(published_at)

        content_html = py_.get(post, "content:encoded", None) or post.get(
            "description", ""
        )
        if not content_html or len(content_html) == 0:
            return {
                "content_html": None,
            }
        raw_url = post.get("link", None)
        url = normalize_url(raw_url, secure=blog.get("secure", True))
        content_html = absolute_urls(content_html, url, blog.get("home_page_url", None))
        # use default author for blog if no post author found and no author header in content
        author = (
            get_contributors(content_html)
            or post.get("dc:creator", None)
            or post.get("author", None)
        )
        if isinstance(author, str):
            authors_ = [{"name": author}]
        elif isinstance(author, list) and author[0] is not None:
            authors_ = [{"name": a} for a in author]
        elif isinstance(author, dict):
            authors_ = [author]
        else:
            authors_ = wrap(blog.get("authors", None))
        authors = [format_author(i, published_at) for i in authors_]

        summary = get_summary(content_html) or ""
        abstract = None
        reference = await get_references(content_html, validate_all)
        relationships = get_relationships(content_html)
        funding_references = wrap(blog.get("funding", None))

        # handle Hugo running on localhost
        if raw_url and raw_url.startswith("http://localhost:1313"):
            raw_url = raw_url.replace(
                "http://localhost:1313", blog.get("home_page_url")
            )
        guid = py_.get(post, "guid.#text", None) or post.get("guid", None) or raw_url
        # handle Hugo running on localhost
        if guid and guid.startswith("http://localhost:1313"):
            guid = guid.replace("http://localhost:1313", blog.get("home_page_url"))
        archive_url = get_archive_url(blog, url, published_at)
        base_url = url
        if blog.get("relative_url", None) == "blog":
            base_url = blog.get("home_page_url", None)
        images = get_images(content_html, base_url, blog.get("home_page_url", None))
        image = py_.get(post, "media:content.@url", None) or py_.get(
            post, "media:thumbnail.@url", None
        )
        try:
            if (
                not image
                and len(images) > 0
                # and isinstance(images[0].get("width", None), int)
                and int(images[0].get("width", 200)) >= 200
                and furl(images[0].get("src", None)).host not in ["latex.codecogs.com"]
            ):
                image = images[0].get("src", None)
        except Exception:
            pass
        # handle Hugo running on localhost
        if image and image.startswith("http://localhost:1313"):
            image = image.replace("http://localhost:1313", blog.get("home_page_url"))

        tags = [
            normalize_tag(i)
            for i in wrap(post.get("category", None))
            if i.split(":")[0] not in EXCLUDED_TAGS
        ][:5]

        return {
            "authors": authors,
            "blog_name": blog.get("title", None),
            "blog_slug": blog.get("slug", None),
            "content_html": content_html,
            "summary": summary,
            "abstract": abstract,
            "published_at": published_at,
            "updated_at": published_at,
            "image": image,
            "images": images,
            "language": detect_language(content_html) or blog.get("language", "en"),
            "category": blog.get("category", None),
            "reference": reference,
            "relationships": relationships,
            "funding_references": presence(funding_references),
            "tags": tags,
            "title": get_title(post.get("title", None)),
            "url": url,
            "archive_url": archive_url,
            "guid": guid,
            "status": blog.get("status", "active"),
        }
    except Exception:
        print(blog.get("slug", None), traceback.format_exc())
        return {}


async def update_rogue_scholar_post(post, blog, validate_all: bool = False):
    """Update Rogue Scholar post."""
    try:

        def format_author(author, published_at):
            """Format author. Optionally lookup real name from username,
            and ORCID from name."""

            return normalize_author(
                author.get("name", None), published_at, author.get("url", None)
            )

        published_at = post.get("published_at")
        updated_at = post.get("updated_at")
        if published_at > updated_at:
            updated_at = published_at
        content_text = post.get("content_text")
        content_html = write_html(content_text)

        # use default author for blog if no post author found and no author header in content
        authors_ = wrap(post.get("authors", None))
        if (
            len(authors_) == 0
            or authors_[0] is None
            or authors_[0].get("name", None) is None
        ):
            authors_ = get_contributors(content_html)
        if (
            authors_ is None
            or len(authors_) == 0
            or authors_[0] is None
            or authors_[0].get("name", None) is None
        ):
            authors_ = wrap(blog.get("authors", None))
        authors = [format_author(i, published_at) for i in authors_ if i]
        summary = get_summary(content_html)
        abstract = post.get("abstract", None)
        abstract = get_abstract(summary, abstract)
        if validate_all:
            reference = await get_references(content_html, validate_all)
        else:
            reference = post.get("reference", None)
        relationships = get_relationships(content_html)
        citations = post.get("citations", [])
        if len(citations) > 0:
            citations = format_citations(citations)
        funding_references = wrap(blog.get("funding", None))
        title = get_title(post.get("title"))
        url = normalize_url(post.get("url"), secure=blog.get("secure", True))
        archive_url = get_archive_url(blog, url, published_at)
        images = get_images(content_html, url, blog["home_page_url"])
        image = post.get("image", None)

        language = post.get("language", None) or detect_language(content_html)
        # optionally remove tag that is used to filter posts
        if blog.get("filter", None) and blog.get("filter", "").startswith("tag"):
            tag = blog.get("filter", "").split(":")[1]
            tags = [
                normalize_tag(i)
                for i in wrap(post.get("tags", None))
                if i != tag and i not in EXCLUDED_TAGS
            ]
        else:
            tags = [
                normalize_tag(i)
                for i in wrap(post.get("tags", None))
                if i not in EXCLUDED_TAGS
            ]
        tags = py_.uniq(tags)[:5]

        return {
            "authors": authors,
            "blog_name": blog.get("title"),
            "blog_slug": blog.get("slug"),
            "content_html": content_html,
            "summary": summary,
            "abstract": abstract,
            "published_at": published_at,
            "updated_at": updated_at,
            "image": image,
            "images": images,
            "language": language,
            "category": blog.get("category", None),
            "reference": reference,
            "relationships": relationships,
            "citations": citations,
            "funding_references": presence(funding_references),
            "tags": tags,
            "title": title,
            "url": url,
            "archive_url": archive_url,
            "guid": post.get("guid"),
            "status": blog.get("status"),
        }
    except Exception:
        print(blog.get("slug", None), traceback.format_exc())
        return {}


def filter_updated_posts(posts, updated_at, key):
    """Filter posts by date updated."""

    def parse_date(date):
        """Parse date into iso8601 string"""
        date_updated = get_date(date)
        return unix_timestamp(date_updated)

    return [x for x in posts if parse_date(x.get(key, None)) > updated_at]


def filter_posts(posts, blog, key):
    """Filter posts if filter is set in blog settings. Used for RSS and Atom feeds."""

    def match_filter(post):
        """Match filter."""
        filters = blog.get("filter", "").split(":")
        if len(filters) != 2 or filters[0] != key:
            return True
        filters = filters[1].split(",")
        if isinstance(post.get(key, None), str):
            return post.get(key, None) in filters
        m = set(post.get(key, None)).intersection(filters)
        return len(m) > 0

    return [x for x in posts if match_filter(x)]


def filter_posts_by_guid(posts, blog, key):
    """Filter posts by GUID that is a DOI."""
    if not blog.get("doi_as_guid", False):
        return posts

    def match_guid(post):
        """GUID is a DOI."""
        doi = validate_doi(post.get(key, None))
        return doi is not None

    return [x for x in posts if match_guid(x)]


def find_post_by_guid(posts, guid, key):
    """Find post by GUID."""

    return next(post for post in posts if post.get(key, None) == guid) or {}


def upsert_single_post(post):
    """Upsert single post."""

    # missing title or publication date
    if not post.get("title", None) or post.get("published_at", None) > int(time.time()):
        return {}

    try:
        response = (
            supabase_admin.table("posts")
            .upsert(
                {
                    "authors": post.get("authors", None),
                    "blog_name": post.get("blog_name", None),
                    "blog_slug": post.get("blog_slug", None),
                    "content_html": post.get("content_html", ""),
                    "images": post.get("images", None),
                    "updated_at": post.get("updated_at", None),
                    "registered_at": post.get("registered_at", 0),
                    "published_at": post.get("published_at", None),
                    "image": post.get("image", None),
                    "language": post.get("language", None),
                    "category": post.get("category", None),
                    "reference": post.get("reference", None),
                    "relationships": post.get("relationships", None),
                    "funding_references": post.get("funding_references", None),
                    "summary": post.get("summary", ""),
                    "abstract": post.get("abstract", None),
                    "tags": post.get("tags", None),
                    "title": post.get("title", None),
                    "url": post.get("url", None),
                    "guid": post.get("guid", None),
                    "status": post.get("status", "active"),
                    "archive_url": post.get("archive_url", None),
                },
                returning="representation",
                ignore_duplicates=False,
                on_conflict="guid",
            )
            .execute()
        )
        data = response.data[0]

        # workaround for comparing two timestamps in supabase
        post_to_update = (
            supabase_admin.table("posts")
            .update(
                {
                    "indexed": data.get("indexed_at", 0) > data.get("updated_at", 1),
                }
            )
            .eq("id", data["id"])
            .execute()
        )

        # upsert InvenioRDM record
        host = furl(environ.get("QUART_INVENIORDM_API", None)).host
        token = environ.get("QUART_INVENIORDM_TOKEN", None)
        legacy_key = environ.get("QUART_SUPABASE_SERVICE_ROLE_KEY", None)
        if not host or not token or not legacy_key:
            return post_to_update.data[0]

        record = (
            supabase.table("posts")
            .select(postsWithCitationsSelect)
            .eq("guid", post.get("guid", None))
            .maybe_single()
            .execute()
        )
        if record is None:
            record = (
                supabase.table("posts")
                .select(postsWithContentSelect)
                .eq("guid", post.get("guid", None))
                .maybe_single()
                .execute()
            )
        status = py_.get(record.data, "blog.status")
        prefix = py_.get(record.data, "blog.prefix")
        if status not in ["active"] or not prefix:
            return post_to_update.data[0]
        metadata = Metadata(record.data, via="jsonfeed")
        if not is_rogue_scholar_doi(metadata.id):
            return post_to_update.data[0]

        kwargs = {"legacy_key": legacy_key}
        record = push_inveniordm(metadata, host, token, **kwargs)
        return record
    except Exception as e:
        print(e)
        return None


def sanitize_html(content_html: str):
    """Sanitize content_html."""
    return nh3.clean(
        content_html,
        tags={"b", "i", "em", "strong", "sub", "sup", "img"},
        attributes={
            "*": ["class"],
            "a": ["href", "rel"],
            "img": ["src", "srcset", "width", "height", "sizes", "alt"],
        },
        link_rel=None,
    )


def get_contributors(content_html: str):
    """Extract contributors from content_html,
    defined as the text after the tag Author(s)</h2>,
    Author(s)</h3> or Author(s)</h4>."""

    def get_name(string):
        """Get name from string."""
        if not string:
            return None
        m = re.search(r"\w+\s\w+", string)
        return m.group(0) if m else None

    def get_url(string):
        """Get url from string."""
        if not string:
            return None
        f = furl(string["href"])
        if f.host not in ["orcid.org"]:
            return None
        return f.url

    def get_contributor(contributor):
        """Get contributor."""
        if not contributor:
            return None
        name = get_name(contributor.text)
        url = get_url(contributor.find("a", href=True))
        if not name:
            return None
        return compact({"name": name, "url": url})

    soup = get_soup(content_html)

    # find author header and extract name and optional orcid
    headers = soup.find_all(["h1", "h2", "h3", "h4"])
    author_header = next(
        (i for i in headers if "Author" in i.text),
        None,
    )
    if not author_header:
        return None
    author_string = author_header.find_next_sibling(["p", "ul", "ol"])
    contributors = []

    # support for multiple authors
    if author_string.name in ["ul", "ol"]:
        for li in author_string.find_all("li"):
            contributors.append(li)
    else:
        contributors.append(author_string)
    return [get_contributor(contributor) for contributor in contributors if contributor]


async def get_references(content_html: str, validate_all: bool = False):
    """Extract references from content_html,
    defined as the text after the tag "References</h2>",
    "References</h3>" or "References</h4>. Store them as references."""

    soup = get_soup(content_html)

    # if references are formatted by citeproc
    list = soup.find("div", {"class": "csl-bib-body"})
    if list:
        tasks = []
        references = list.find_all("div", class_="csl-entry")
        for reference in references:
            task = format_citeproc_reference(reference, validate_all)
            tasks.append(task)
        formatted_references = py_.compact(await asyncio.gather(*tasks))
        return formatted_references

    # if references are formatted by kcite, using [cite] shortcodes
    cite_re = re.findall(r"\[cite\](.+?)\[/cite\]", content_html)
    if cite_re:
        references = py_.uniq(cite_re)
        tasks = []
        for reference in references:
            ref = normalize_doi(reference)
            if ref:
                task = format_reference(ref, True)
                tasks.append(task)
        formatted_references = py_.compact(await asyncio.gather(*tasks))
        return formatted_references

    # if there is a references section
    reference_html = re.split(
        r"(?:References|Reference|Referenzen|Bibliography|Literature|Literatur|Footnotes|References:|Works cited)(?:<\/strong>)?<\/(?:h1|h2|h3|h4)>",
        content_html,
        maxsplit=2,
    )
    if len(reference_html) == 1:
        return []

    # if references use an (ordered or unordered) list
    soup = get_soup(reference_html[1])
    list = soup.ol or soup.ul
    references = []
    if list:
        references = list.find_all("li")
    if len(references) > 0:
        tasks = []
        for reference in references:
            task = format_list_reference(reference, validate_all)
            tasks.append(task)
        formatted_references = py_.compact(await asyncio.gather(*tasks))
        return formatted_references

    # fallback if references are not in yet found
    # strip optional text after references, using <hr>, <hr />, <h1, <h2, <h3, <h4, <blockquote as tag
    reference_html[1] = re.split(
        r"(?:<hr \/>|<hr>|<h1|<h2|<h3|<h4|<blockquote)", reference_html[1], maxsplit=2
    )[0]

    urls = get_urls(reference_html[1])
    if not urls or len(urls) == 0:
        return []

    tasks = []
    for url in urls:
        task = format_reference(url, validate_all)
        tasks.append(task)

    formatted_references = py_.compact(await asyncio.gather(*tasks))
    return formatted_references


async def get_jsonfeed_references(references: list, validate_all: bool = False):
    """Extract references from jsonfeed _references field."""
    tasks = []
    for reference in references:
        task = format_json_reference(reference, validate_all)
        tasks.append(task)

    formatted_references = py_.compact(await asyncio.gather(*tasks))
    return formatted_references


async def get_funding(content_html: str, validate_all: bool = False) -> list:
    """Extract funding from content_html, optionally lookup award metadata."""
    return []


async def get_funding_references(funding_references: Optional[dict]) -> list:
    """get json feed funding references."""

    if funding_references is None:
        return []

    def format_funding(funding) -> dict:
        """format funding."""
        identifier = normalize_ror(
            py_.get(funding, "funder.id") or py_.get(funding, "funder.ror")
        )
        award_number = py_.get(funding, "award.number")
        award_uri = py_.get(funding, "award.uri")
        if award_uri and award_uri.split(":")[0] == "cordis.project":
            award_number = award_uri.split(":")[1]
            award_uri = f"https://cordis.europa.eu/project/id/{award_number}"
        elif award_uri and award_uri.split(":")[0] == "drc.filenumber":
            award_number = award_uri.split(":")[1]
            award_uri = f"https://www.nwo.nl/en/projects/{award_number}"
        elif award_uri and award_uri.split(":")[0] == "grants.gov":
            award_number = award_uri.split(":")[1]
            award_uri = f"https://www.grants.gov/web/grants/view-opportunity.html?oppId={award_number}"
        return compact(
            {
                "funderName": py_.get(funding, "funder.name"),
                "funderIdentifier": identifier,
                "funderIdentifierType": "ROR" if identifier else None,
                "awardTitle": py_.get(funding, "award.title"),
                "awardNumber": award_number,
                "awardUri": award_uri,
            }
        )

    return [format_funding(i) for i in wrap(funding_references)]


def get_archive_url(blog: dict, url: str, published_at: int) -> Optional[str]:
    """Get archive url."""

    if not blog.get("archive_collection", None):
        return None

    f = furl(url)
    if blog.get("archive_host", None):
        f.host = blog["archive_host"]
    archive_timestamp = blog.get("archive_timestamps", None)
    if not archive_timestamp or len(archive_timestamp) == 0:
        return None
    archive_timestamp = get_datetime_from_time(str(archive_timestamp[-1]))
    if unix_timestamp(archive_timestamp) < published_at:
        return None

    return f"https://wayback.archive-it.org/{blog['archive_collection']}/{archive_timestamp}/{f.url}"


def normalize_blogger_url(url: str) -> str:
    """Normalize blogger url."""
    f = furl(url)
    if f.host == "www.earlham.edu":
        f.host = "legacy.earlham.edu"
    if "fosblog.html" in f.path.segments:
        f.path.segments.remove("fosblog.html")
    return f.url


def get_title(content_html: str):
    """Sanitize title."""
    if not content_html:
        return None
    content_html = html.unescape(content_html).strip()
    content_html = re.sub(r"(<br>|<p>)", " ", content_html)
    content_html = re.sub(r"(h1>|h2>|h3>|h4>)", "strong>", content_html)

    # remove strong tags around the whole title
    content_html = re.sub(r"^<strong>(.*)<\/strong>$", "$1", content_html)
    sanitized = nh3.clean(
        content_html, tags={"b", "i", "em", "strong", "sub", "sup"}, attributes={}
    )
    return sanitized


def get_image(images: list, width: int = 200):
    """Get first image with width >= 200."""
    if not images or len(images) == 0:
        return None
    try:
        return next(
            (
                image.get("src", None)
                for image in images
                if int(image.get("width", 200)) >= width
            ),
            None,
        )
    except ValueError:
        return None


def get_summary(content_html: str = None, maxlen: int = 450):
    """Get summary from excerpt or content_html."""
    if not content_html:
        return None
    content_html = re.sub(r"(<br>|<br/>|<p>|</pr>)", " ", content_html)
    content_html = re.sub(r"(h1>|h2>|h3>|h4>)", "strong> ", content_html)

    sanitized = nh3.clean(
        content_html,
        tags={"b", "i", "em", "strong", "sub", "sup"},
        clean_content_tags={"figcaption", "figure", "blockquote"},
        attributes={},
    )
    sanitized = re.sub(r"\n+", " ", sanitized).strip()

    # workaround to remove script tag
    script_tag = """document.addEventListener("DOMContentLoaded", () =&gt; {     // Add skip link to the page     let element = document.getElementById("quarto-header");     let skiplink =       '&lt;a id="skiplink" class="visually-hidden-focusable" href="#quarto-document-content"&gt;Skip to main content&lt;/a&gt;';     element.insertAdjacentHTML("beforebegin", skiplink);   });"""
    sanitized = sanitized.replace(script_tag, "")

    truncated = py_.truncate(sanitized, maxlen, omission="", separator=" ")

    # remove incomplete last sentence
    if len(truncated) > 0 and truncated[-1] not in [".", "!", "?", ";"]:
        sentences = re.split(r"(?<=\w{3}[.!?;])\s+", truncated)
        if len(sentences) > 1:
            truncated = " ".join(sentences[:-1])
        else:
            truncated = sentences[0]

    # make sure html tags are closed and trailing whitespace is removed
    soup = get_soup(truncated)
    string = soup.prettify()
    return string.strip()


def get_abstract(summary: str, abstract: Optional[str]):
    """Get abstract if not beginning of post.
    Use Levenshtein distance to compare summary and abstract."""
    if abstract is None or summary is None:
        return None
    le = min(len(abstract), 100)
    rat = ratio(summary[:le], abstract[:le])
    return abstract if rat <= 0.75 else None


def get_relationships(content_html: str):
    """Get relationships from content_html. Extract links from
    Acknowledgments section,defined as the text after the tag
    "Acknowledgments</h2>", "Acknowledgments</h3>" or "Acknowledgments</h4>.
    In addition, extract links to reviews from an optional Editorial Assessment section."""

    try:
        relationships_html = re.split(
            r"Acknowledgments<\/(?:h1|h2|h3|h4)>",
            content_html,
            maxsplit=2,
        )

        reviews_html = re.split(
            r"Editorial Assessment<\/(?:h1|h2|h3|h4)>",
            content_html,
            maxsplit=2,
        )

        if len(relationships_html) == 1 and len(reviews_html) == 1:
            return []

        # strip optional text after notes, using <hr>, <hr />, <h2, <h3, <h4 as tag
        relationships_html[1] = re.split(
            r"(?:<hr \/>|<hr>|<h2|<h3|<h4)", relationships_html[1], maxsplit=2
        )[0]
        if len(reviews_html) == 2:
            reviews_html[1] = re.split(
                r"(?:<hr \/>|<hr>|<h2|<h3|<h4)", reviews_html[1], maxsplit=2
            )[0]

        # split notes into sentences and classify relationship type for each sentence
        sentences = re.split(r"(?<=\w{3}[.!?;])\s+", relationships_html[1])
        if len(reviews_html) == 2:
            sentences += re.split(r"(?<=\w{3}[.!?;])\s+", reviews_html[1])

        def extract_url(sentence):
            """Extract url from sentence."""
            sentence = sentence.strip()
            urls = get_urls(sentence)
            if not urls or len(urls) == 0:
                return None
            # detect type of relationship
            _type = None
            if re.search("(originally published|cross-posted)", sentence):
                _type = "IsIdenticalTo"
            elif re.search("peer-reviewed version", sentence):
                _type = "IsPreprintOf"
            elif re.search("work was funded", sentence):
                _type = "HasAward"
            elif re.search("have reviewed", sentence):
                _type = "HasReview"
            if _type is None:
                return None
            return {"type": _type, "urls": urls}

        relationships = [extract_url(i) for i in sentences]
        return [i for i in relationships if i is not None]
    except Exception as e:
        print(e)
        return []


def absolute_urls(content_html: str, url: str, home_page_url: str):
    """Make all links absolute in content_html."""

    try:
        soup = get_soup(content_html)
        if not soup:
            return content_html
        for a in soup.find_all("a"):
            href = a.get("href", None)
            if href is not None:
                href = get_src_url(href, url, home_page_url)
                a["href"] = href
        for link in soup.find_all("link"):
            href = link.get("href", None)
            if href is not None:
                href = get_src_url(href, url, home_page_url)
                link["href"] = href
        for img in soup.find_all("img"):
            src = img.get("src", None)
            if src is not None:
                src = get_src_url(src, url, home_page_url)
                img["src"] = src
        return str(soup)
    except Exception as e:
        print(e)
        print(traceback.format_exc())
        return content_html


def get_images(content_html: str, url: str, home_page_url: str):
    """Extract images from content_html."""

    try:

        def extract_img(image):
            """Extract url from link."""
            src = image.attrs.get("src", None)
            if src is not None:
                src = get_src_url(src, url, home_page_url)
            srcset = image.attrs.get("srcset", None)

            if isinstance(srcset, str):
                srcset = srcset.split(", ")
                srcset = [i.split(" ")[0] for i in srcset]
                srcset = [get_src_url(i, url, home_page_url) for i in srcset]
                srcset = ", ".join(srcset)
            alt = image.attrs.get("alt", None)

            if alt:
                alt = alt.strip()

            return compact(
                {
                    "src": src,
                    "srcset": srcset,
                    "width": image.attrs.get("width", None),
                    "height": image.attrs.get("height", None),
                    "sizes": image.attrs.get("sizes", None),
                    "alt": alt if alt and len(alt) > 0 else None,
                }
            )

        soup = get_soup(content_html)
        if not soup:
            return []

        # find images in img tags
        images = [extract_img(i) for i in soup.find_all("img")]

        # find images in figure tags
        def extract_figure(figure):
            """Extract url from link."""
            src = figure.find("img") and figure.find("img").attrs.get("src", None)
            if not src:
                src = figure.find("a") and figure.find("a").attrs.get("href", None)
            if src:
                src = get_src_url(src, url, home_page_url)
            alt = figure.find("figcaption") and figure.find("figcaption").text.strip()

            return compact(
                {
                    "src": src,
                    "alt": alt if alt and len(alt) > 0 else None,
                }
            )

        figures = [extract_figure(i) for i in soup.find_all("figure")]
        figures = [
            x
            for x in figures
            if x.get("src", None) is not None
            and x.get("src", None).split(".").pop()
            in ["jpg", "jpeg", "png", "gif", "svg"]
        ]

        # find images in links
        def extract_link(link):
            """Extract url from link."""
            src = link.get("href", None)
            if src:
                src = get_src_url(src, url, home_page_url)
            alt = link.text.strip()

            return compact(
                {
                    "src": src,
                    "alt": alt if alt and len(alt) > 0 else None,
                }
            )

        links = [extract_link(i) for i in soup.find_all("a")]
        links = [
            x
            for x in links
            if x.get("src", None) is not None
            and x.get("src", None).split(".").pop()
            in ["jpg", "jpeg", "png", "gif", "svg"]
        ]
        return images + figures + links
    except Exception as e:
        print(e)
        print(traceback.format_exc())
        return []


def get_urls(content_html: str):
    """Extract urls from html."""

    try:
        soup = get_soup(content_html)

        def extract_url(link):
            """Extract url from link."""
            return link.get("href")

        urls = [extract_url(i) for i in soup.find_all("a") if i.get("href", None)]

        if not urls or len(urls) == 0:
            return []

        def clean_url(url):
            """Clean url."""
            url = normalize_url(url)
            if not url:
                return None
            f = furl(url)
            if validate_doi(url):
                if f.scheme == "http":
                    f.scheme = "https"
                if f.host == "dx.doi.org":
                    f.host = "doi.org"
                url = f.url
            else:
                if not f.host:
                    return None
                url = url.lower()
            return url

        urls = [clean_url(i) for i in urls]
        return py_.uniq(urls)
    except Exception as e:
        print(e)
        print(traceback.format_exc())
        return []


def validate_funding(funding: list) -> Optional[list]:
    """Validate funding."""

    def format_funding(item):
        """Format funding."""
        if not item.get("award", None):
            return item
        if py_.get(item, "award.number"):
            award = get_award(py_.get(item, "award.number"))
            if award:
                item["award"] = award
        return item

    return py_.uniq([format_funding(i) for i in funding])


def get_award(id: Optional[str]) -> Optional[dict]:
    """Get award from award ID"""
    file_path = path.join(path.dirname(__file__), "../pandoc/awards.yaml")
    with open(file_path, encoding="utf-8") as file:
        string = file.read()
        awards = yaml.safe_load(string)
    award = py_.find(awards, lambda x: x["id"] == id)
    if id is None or award is None:
        return None
    return award


async def delete_draft_record(rid: str):
    """Delete an InvenioRDM draft record."""
    if rid is None:
        return None
    try:
        url = f"{environ['QUART_INVENIORDM_API']}/api/records/{rid}/draft"
        headers = {
            "Content-Type": "application/octet-stream",
            "Authorization": f"Bearer {environ['QUART_INVENIORDM_TOKEN']}",
        }
        async with httpx.AsyncClient() as client:
            response = await client.delete(url, headers=headers, timeout=10.0)
            if response.status_code != 204:
                print(response.json())
        return {"message": f"Draft record {rid} deleted"}
    except Exception as error:
        print(error)
        return None


async def delete_all_draft_records():
    """Delete all InvenioRDM draft records."""
    try:
        number_of_records = await get_number_of_draft_records()
        pages = ceil(number_of_records / 50)
        for page in range(1, pages + 1):
            message = await delete_draft_records(page)
            print(message)
        return {"message": f"{number_of_records} draft records deleted"}
    except Exception as error:
        print(error)
        return None


async def delete_draft_records(page: int = 1):
    """Delete InvenioRDM draft records."""
    try:
        url = f"{environ['QUART_INVENIORDM_API']}/api/user/records?q=is_published:false&page={page}&size=50&sort=updated-desc"
        headers = {
            "Content-Type": "application/octet-stream",
            "Authorization": f"Bearer {environ['QUART_INVENIORDM_TOKEN']}",
        }
        response = httpx.get(url, headers=headers, timeout=10)
        records = py_.get(response.json(), "hits.hits", [])
        n = py_.get(response.json(), "hits.total", 0)
        await asyncio.gather(*[delete_draft_record(record["id"]) for record in records])
        return {"message": f"{n} draft records deleted"}
    except Exception as error:
        print(error)
        return None


async def get_number_of_draft_records():
    """Get number of InvenioRDM draft records."""
    try:
        url = f"{environ['QUART_INVENIORDM_API']}/api/user/records?q=is_published:false"
        headers = {
            "Content-Type": "application/octet-stream",
            "Authorization": f"Bearer {environ['QUART_INVENIORDM_TOKEN']}",
        }
        response = httpx.get(url, headers=headers, timeout=10)
        n = py_.get(response.json(), "hits.total", 0)
        return n
    except Exception as error:
        print(error)
        return None


async def get_citations(doi: Optional[str]) -> list:
    """Get citations for a DOI."""
    try:
        if doi is None:
            return []
        response = (
            supabase.table("citations")
            .select("citation")
            .eq("doi", doi)
            .eq("validated", True)
            .order("published_at", desc=False)
            .order("updated_at", desc=False)
            .execute()
        )
        if not response:
            return []
        tasks = []
        for citation in response.data:
            task = format_reference(citation.get("citation", None), True)
            tasks.append(task)
        return py_.compact(await asyncio.gather(*tasks))
    except Exception as error:
        print(error)
        return None


def format_citations(citations: list) -> list:
    """Format citations."""

    def format_citation(citation):
        """Format citation in inveniordm reference format."""

        unstructured = citation.get("unstructured", None)

        if citation.get("citation", None):
            # remove duplicate ID from unstructured reference
            unstructured = unstructured.replace(citation.get("citation"), "")

        # remove optional trailing whitespace
        unstructured = unstructured.rstrip()

        return compact(
            {
                "identifier": citation.get("citation", None),
                "scheme": "doi",
                "reference": unstructured,
            }
        )

    return [
        format_citation(citation)
        for citation in citations
        if citation.get("validated", False)
    ]
