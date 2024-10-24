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
    normalize_id,
    validate_url,
    validate_prefix,
)
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
    wrap,
    compact,
    fix_xml,
    get_markdown,
    write_html,
    validate_uuid,
    id_as_str,
    EXCLUDED_TAGS,
)
from api.works import get_single_work
from api.supabase_client import (
    supabase_admin_client as supabase_admin,
    supabase_client as supabase,
    postsWithContentSelect,
)


async def extract_all_posts(page: int = 1, update_all: bool = False):
    """Extract all posts."""

    blogs = (
        supabase.table("blogs")
        .select("slug")
        .in_("status", ["active"])
        .order("slug", desc=False)
        .execute()
    )
    tasks = []
    for blog in blogs.data:
        task = extract_all_posts_by_blog(blog["slug"], page, update_all)
        tasks.append(task)

    raw_results = await asyncio.gather(*tasks)

    # flatten list of lists
    results = []
    for result in raw_results:
        if result:
            results.append(result[0])

    return results


async def update_all_posts(page: int = 1):
    """Update all posts."""

    blogs = (
        supabase.table("blogs")
        .select("slug")
        .in_("status", ["active", "archived", "pending"])
        .order("title", desc=False)
        .execute()
    )
    tasks = []
    for blog in blogs.data:
        task = update_all_posts_by_blog(blog["slug"], page)
        tasks.append(task)

    raw_results = await asyncio.gather(*tasks)

    # flatten list of lists
    results = []
    for result in raw_results:
        if result:
            results.append(result[0])

    return results


async def extract_all_posts_by_blog(
    slug: str, page: int = 1, offset: Optional[int] = None, update_all: bool = False
):
    """Extract all posts by blog."""

    try:
        response = (
            supabase.table("blogs")
            .select(
                "id, slug, feed_url, current_feed_url, home_page_url, archive_prefix, feed_format, created_at, updated_at, mastodon, generator, generator_raw, language, category, favicon, title, description, category, status, user_id, authors, use_api, relative_url, filter, secure"
            )
            .eq("slug", slug)
            .maybe_single()
            .execute()
        )
        blog = response.data
        if not blog:
            return {}
        if page == 1:
            url = furl(blog.get("current_feed_url", None) or blog.get("feed_url", None))
        else:
            url = furl(blog.get("feed_url", None))
        generator = (
            blog.get("generator", "").split(" ")[0]
            if blog.get("generator", None)
            else None
        )
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
                        filters = blog.get("filter", "").split(":")
                        if len(filters) == 2 and filters[0] == "category":
                            if int(filters[1]) < 0:
                                # exclude category if prefixed with minus sign
                                params["categories_exclude"] = filters[1][1:]
                            else:
                                # otherwise include category
                                params["categories"] = filters[1]
                        elif len(filters) == 2 and filters[0] == "tag":
                            if int(filters[1]) < 0:
                                # exclude tag if prefixed with minus sign
                                params["tags_exclude"] = filters[1][1:]
                            else:
                                # otherwise include tag
                                params["tags"] = filters[1]

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
                params = compact({"format": "json", "offset": offset})
            case _:
                params = {}

        feed_url = url.set(params).url
        blog_with_posts = {}
        print(f"Extracting posts from {blog['slug']} at {feed_url}.")

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
                        posts = filter_updated_posts(posts, blog, key="post_date")
                except httpx.TimeoutException:
                    print(f"Timeout error for feed {feed_url}.")
                    posts = []
                except httpx.HTTPError as e:
                    capture_exception(e)
                    posts = []
                extract_posts = [extract_substack_post(x, blog) for x in posts]
            blog_with_posts["entries"] = await asyncio.gather(*extract_posts)
        elif generator == "WordPress" and blog["use_api"]:
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.get(
                        feed_url, timeout=10.0, follow_redirects=True
                    )
                    response.raise_for_status()
                    # filter out error messages that are not valid json
                    json_start = response.text.find("[{")
                    response = response.text[json_start:]
                    posts = JSON.loads(response)
                    if not update_all:
                        posts = filter_updated_posts(posts, blog, key="modified_gmt")
                except httpx.TimeoutException:
                    print(f"Timeout error for feed {feed_url}.")
                    posts = []
                except httpx.HTTPError as e:
                    capture_exception(e)
                    posts = []
                extract_posts = [extract_wordpress_post(x, blog) for x in posts]
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
                        posts = filter_updated_posts(posts, blog, key="modified")
                except httpx.TimeoutException:
                    print(f"Timeout error for feed {feed_url}.")
                    posts = []
                except httpx.HTTPError as e:
                    capture_exception(e)
                    posts = []
                extract_posts = [extract_wordpresscom_post(x, blog) for x in posts]
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
                        posts = filter_updated_posts(posts, blog, key="updated_at")
                except httpx.TimeoutException:
                    print(f"Timeout error for feed {feed_url}.")
                    posts = []
                except httpx.HTTPError as e:
                    capture_exception(e)
                    posts = []
                extract_posts = [extract_ghost_post(x, blog) for x in posts]
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
                        posts = filter_updated_posts(posts, blog, key="pubDate")
                except httpx.TimeoutException:
                    print(f"Timeout error for feed {feed_url}.")
                    posts = []
                except httpx.HTTPError as e:
                    capture_exception(e)
                    posts = []
                extract_posts = [extract_squarespace_post(x, blog) for x in posts]
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
                        posts = filter_updated_posts(posts, blog, key="date_modified")
                    posts = posts[start_page:end_page]
                except httpx.TimeoutException:
                    print(f"Timeout error for feed {feed_url}.")
                    posts = []
                except httpx.HTTPError as e:
                    capture_exception(e)
                    posts = []
                extract_posts = [extract_json_feed_post(x, blog) for x in posts]
            blog_with_posts["entries"] = await asyncio.gather(*extract_posts)
        elif blog["feed_format"] == "application/atom+xml":
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.get(
                        feed_url, timeout=10.0, follow_redirects=True
                    )
                    response.raise_for_status()
                    # fix malformed xml
                    xml = fix_xml(response.read())
                    json = xmltodict.parse(
                        xml, dict_constructor=dict, force_list={"entry"}
                    )
                    posts = py_.get(json, "feed.entry", [])
                    if not update_all:
                        posts = filter_updated_posts(posts, blog, key="published")
                    if blog.get("filter", None):
                        posts = filter_posts(posts, blog, key="category")
                    posts = posts[start_page:end_page]
                except httpx.TimeoutException:
                    print(f"Timeout error for feed {feed_url}.")
                    posts = []
                except httpx.HTTPError as e:
                    capture_exception(e)
                    posts = []
            extract_posts = [extract_atom_post(x, blog) for x in posts]
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
                        posts = filter_updated_posts(posts, blog, key="pubDate")
                    if blog.get("filter", None):
                        posts = filter_posts(posts, blog, key="category")
                    posts = posts[start_page:end_page]
                except httpx.TimeoutException:
                    print(f"Timeout error for feed {feed_url}.")
                    posts = []
                except httpx.HTTPError as e:
                    capture_exception(e)
                    posts = []
            extract_posts = [extract_rss_post(x, blog) for x in posts]
            blog_with_posts["entries"] = await asyncio.gather(*extract_posts)
        else:
            blog_with_posts["entries"] = []
        if blog.get("status", None) not in ["pending", "active"]:
            return blog_with_posts["entries"]
        return [upsert_single_post(i) for i in blog_with_posts["entries"]]
    except Exception as e:
        print(f"{e} error.")
        print(traceback.format_exc())
        return []


async def update_all_posts_by_blog(slug: str, page: int = 1):
    """Update all posts by blog."""

    try:
        response = (
            supabase.table("blogs")
            .select(
                "id, slug, feed_url, current_feed_url, home_page_url, archive_prefix, feed_format, created_at, updated_at, mastodon, generator, generator_raw, language, category, favicon, title, description, category, status, user_id, authors, use_api, relative_url, filter, secure"
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
        update_posts = [update_rogue_scholar_post(x, blog) for x in response.data]
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


async def update_single_post(slug: str, suffix: Optional[str] = None):
    """Update single post"""
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
        blog = response.data.get("blog", None)
        if not blog:
            return {"error": "Blog not found."}, 404
        post = py_.omit(response.data, "blog")
        updated_post = await update_rogue_scholar_post(post, blog)
        response = upsert_single_post(updated_post)
        return response
    except Exception:
        print(traceback.format_exc())
        return {}


async def extract_wordpress_post(post, blog):
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
        # use default author for blog if no post author found
        authors_ = wrap(py_.get(post, "_embedded.author", None))
        if len(authors_) == 0 or authors_[0].get("name", None) is None:
            authors_ = wrap(blog.get("authors", None))
        authors = [format_author(i, published_at) for i in authors_]
        content_html = py_.get(post, "content.rendered", "")
        content_text = get_markdown(content_html)
        summary = get_summary(content_html)
        abstract = get_summary(py_.get(post, "excerpt.rendered", ""))
        abstract = get_abstract(summary, abstract)
        reference = await get_references(content_html)
        relationships = get_relationships(content_html)
        url = normalize_url(post.get("link", None), secure=blog.get("secure", True))
        archive_url = (
            blog["archive_prefix"] + url if blog.get("archive_prefix", None) else None
        )
        images = get_images(content_html, url, blog["home_page_url"])
        image = (
            py_.get(post, "_embedded.wp:featuredmedia[0].source_url", None)
            or py_.get(post, "yoast_head_json.og_image[0].url", None)
            or post.get("jetpack_featured_media_url", None)
        ) or get_image(images)

        # optionally remove category that is used to filter posts
        if blog.get("filter", None) and blog.get("filter", "").startswith("category"):
            cat = blog.get("filter", "").split(":")[1]
            categories = [
                normalize_tag(i.get("name", None))
                for i in wrap(py_.get(post, "_embedded.wp:term.0", None))
                if i.get("id", None) != int(cat)
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
            "content_text": content_text,
            "summary": summary,
            "abstract": abstract,
            "published_at": published_at,
            "updated_at": unix_timestamp(post.get("modified_gmt", None)),
            "image": image,
            "images": images,
            "language": detect_language(content_html),
            "category": blog.get("category", None),
            "reference": reference,
            "relationships": relationships,
            "tags": terms,
            "title": py_.get(post, "title.rendered", ""),
            "url": url,
            "archive_url": archive_url,
            "guid": py_.get(post, "guid.rendered", None),
            "status": blog.get("status", "active"),
        }
    except Exception:
        print(blog.get("slug", None), traceback.format_exc())
        return {}


async def extract_wordpresscom_post(post, blog):
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
        content_text = get_markdown(content_html)
        summary = get_summary(post.get("content", ""))
        abstract = get_summary(post.get("excerpt", None))
        abstract = get_abstract(summary, abstract)
        reference = await get_references(content_html)
        relationships = get_relationships(content_html)
        url = normalize_url(post.get("URL", None), secure=blog.get("secure", True))
        archive_url = (
            blog["archive_prefix"] + url if blog.get("archive_prefix", None) else None
        )
        images = get_images(content_html, url, blog.get("home_page_url", None))
        image = get_image(images)
        tags = [
            normalize_tag(i)
            for i in post.get("categories", None).keys()
            if i.split(":")[0] not in EXCLUDED_TAGS
        ][:5]

        return {
            "authors": authors,
            "blog_name": blog.get("title", None),
            "blog_slug": blog.get("slug", None),
            "content_text": content_text,
            "summary": summary,
            "abstract": abstract,
            "published_at": published_at,
            "updated_at": unix_timestamp(post.get("modified", None)),
            "image": image,
            "images": images,
            "language": detect_language(content_html),
            "category": blog.get("category", None),
            "reference": reference,
            "relationships": relationships,
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


async def extract_ghost_post(post, blog):
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
        content_text = get_markdown(content_html)

        # don't use excerpt as summary, because it's not html
        summary = get_summary(content_html)
        abstract = get_summary(post.get("excerpt", ""))
        abstract = get_abstract(summary, abstract)
        reference = await get_references(content_html)
        relationships = get_relationships(content_html)
        url = normalize_url(post.get("url", None), secure=blog.get("secure", True))
        archive_url = (
            blog["archive_prefix"] + url if blog.get("archive_prefix", None) else None
        )
        images = get_images(content_html, url, blog.get("home_page_url", None))
        image = post.get("feature_image", None) or get_image(images)
        tags = [
            normalize_tag(i.get("name", None))
            for i in post.get("tags", None)
            if i.get("name", "").split(":")[0] not in EXCLUDED_TAGS
        ][:5]

        return {
            "authors": authors,
            "blog_name": blog.get("title", None),
            "blog_slug": blog.get("slug", None),
            "content_text": content_text,
            "summary": summary,
            "abstract": abstract,
            "published_at": published_at,
            "updated_at": unix_timestamp(post.get("updated_at", None)),
            "image": image,
            "images": images,
            "language": detect_language(content_html),
            "category": blog.get("category", None),
            "reference": reference,
            "relationships": relationships,
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


async def extract_substack_post(post, blog):
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
        content_html = post.get("body_html", "")
        content_text = get_markdown(content_html)
        summary = get_summary(post.get("description", None))
        abstract = get_summary(content_html)
        abstract = get_abstract(summary, abstract)
        reference = await get_references(content_html)
        relationships = get_relationships(content_html)
        url = normalize_url(
            post.get("canonical_url", None), secure=blog.get("secure", True)
        )
        archive_url = (
            blog["archive_prefix"] + url if blog.get("archive_prefix", None) else None
        )
        images = get_images(content_html, url, blog.get("home_page_url", None))
        image = post.get("cover_image", None) or get_image(images)
        tags = [
            normalize_tag(i.get("name"))
            for i in wrap(post.get("postTags", None))
            if i.get("name", "").split(":")[0] not in EXCLUDED_TAGS
        ][:5]

        return {
            "authors": authors,
            "blog_name": blog.get("title", None),
            "blog_slug": blog.get("slug", None),
            "content_text": content_text,
            "summary": summary,
            "abstract": abstract,
            "published_at": published_at,
            "updated_at": published_at,
            "image": image,
            "images": images,
            "language": detect_language(content_html),
            "category": blog.get("category", None),
            "reference": reference,
            "relationships": relationships,
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


async def extract_squarespace_post(post, blog):
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
        content_text = get_markdown(content_html)
        summary = get_summary(content_html)
        abstract = get_summary(post.get("excerpt", ""))
        if abstract is not None:
            abstract = get_abstract(summary, abstract)

        reference = await get_references(content_html)
        relationships = get_relationships(content_html)
        url = normalize_url(
            f'{blog.get("home_page_url", "")}/{post.get("urlId","")}',
            secure=blog.get("secure", True),
        )
        archive_url = (
            blog["archive_prefix"] + url if blog.get("archive_prefix", None) else None
        )
        images = get_images(content_html, url, blog.get("home_page_url", None))
        image = post.get("assetUrl", None) or get_image(images)
        tags = [
            normalize_tag(i)
            for i in wrap(post.get("categories", None))
            if i.split(":")[0] not in EXCLUDED_TAGS
        ][:5]

        return {
            "authors": authors,
            "blog_name": blog.get("title", None),
            "blog_slug": blog.get("slug", None),
            "content_text": content_text,
            "summary": summary,
            "abstract": abstract,
            "published_at": published_at,
            "updated_at": updated_at,
            "image": image,
            "images": images,
            "language": detect_language(content_html),
            "category": blog.get("category", None),
            "reference": reference,
            "relationships": relationships,
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


async def extract_json_feed_post(post, blog):
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
        content_text = get_markdown(content_html)
        summary = get_summary(content_html)
        abstract = None
        reference = await get_references(content_html)
        relationships = get_relationships(content_html)
        url = normalize_url(post.get("url", None), secure=blog.get("secure", True))
        archive_url = (
            blog["archive_prefix"] + url if blog.get("archive_prefix", None) else None
        )
        base_url = url
        if blog.get("relative_url", None) == "blog":
            base_url = blog.get("home_page_url", None)
        images = get_images(content_html, base_url, blog.get("home_page_url", None))
        image = py_.get(post, "media:thumbnail.@url", None) or get_image(images)
        tags = [
            normalize_tag(i)
            for i in wrap(post.get("tags", None))
            if i.split(":")[0] not in EXCLUDED_TAGS
        ][:5]

        return {
            "authors": authors,
            "blog_name": blog.get("title", None),
            "blog_slug": blog.get("slug", None),
            "content_text": content_text,
            "summary": summary,
            "abstract": abstract,
            "published_at": published_at,
            "updated_at": unix_timestamp(post.get("date_modified", None)),
            "image": image,
            "images": images,
            "language": detect_language(content_html),
            "category": blog.get("category", None),
            "reference": reference,
            "relationships": relationships,
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


async def extract_atom_post(post, blog):
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

        # use default authors for blog if no post authors found
        authors_ = wrap(post.get("author", None))
        if len(authors_) == 0 or authors_[0].get("name", None) is None:
            authors_ = wrap(blog.get("authors", None))
        authors = [format_author(i, published_at) for i in authors_]

        # workaround, as content should be encodes as CDATA block
        content_html = html.unescape(py_.get(post, "content.#text", ""))
        content_text = get_markdown(content_html)
        title = get_title(py_.get(post, "title.#text", None)) or get_title(
            post.get("title", None)
        )
        summary = get_summary(content_html)
        abstract = py_.get(post, "summary.#text", None)
        abstract = get_abstract(summary, abstract)
        reference = await get_references(content_html)
        relationships = get_relationships(content_html)

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
        archive_url = (
            blog["archive_prefix"] + url if blog.get("archive_prefix", None) else None
        )
        base_url = url
        if blog.get("relative_url", None) == "blog":
            base_url = blog.get("home_page_url", None)
        images = get_images(content_html, base_url, blog.get("home_page_url", None))
        image = py_.get(post, "media:thumbnail.@url", None) or get_image(images)
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
            "content_text": content_text,
            "summary": summary,
            "abstract": abstract,
            "published_at": published_at,
            "updated_at": updated_at,
            "image": image,
            "images": images,
            "language": detect_language(content_html),
            "category": blog.get("category", None),
            "reference": reference,
            "relationships": relationships,
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


async def extract_rss_post(post, blog):
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

        content_text = get_markdown(content_html)

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
        reference = await get_references(content_html)
        relationships = get_relationships(content_html)
        raw_url = post.get("link", None)
        url = normalize_url(raw_url, secure=blog.get("secure", True))
        guid = py_.get(post, "guid.#text", None) or post.get("guid", None) or raw_url
        archive_url = (
            blog["archive_prefix"] + url if blog.get("archive_prefix", None) else None
        )
        base_url = url
        if blog.get("relative_url", None) == "blog":
            base_url = blog.get("home_page_url", None)
        images = get_images(content_html, base_url, blog.get("home_page_url", None))
        image = py_.get(post, "media:content.@url", None) or py_.get(
            post, "media:thumbnail.@url", None
        )
        if (
            not image
            and len(images) > 0
            # and isinstance(images[0].get("width", None), int)
            and int(images[0].get("width", 200)) >= 200
            and furl(images[0].get("src", None)).host not in ["latex.codecogs.com"]
        ):
            image = images[0].get("src", None)
        tags = [
            normalize_tag(i)
            for i in wrap(post.get("category", None))
            if i.split(":")[0] not in EXCLUDED_TAGS
        ][:5]

        return {
            "authors": authors,
            "blog_name": blog.get("title", None),
            "blog_slug": blog.get("slug", None),
            "content_text": content_text,
            "summary": summary,
            "abstract": abstract,
            "published_at": published_at,
            "updated_at": published_at,
            "image": image,
            "images": images,
            "language": detect_language(content_html),
            "category": blog.get("category", None),
            "reference": reference,
            "relationships": relationships,
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


async def update_rogue_scholar_post(post, blog):
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
            len(authors_) == 0
            or authors_[0] is None
            or authors_[0].get("name", None) is None
        ):
            authors_ = wrap(blog.get("authors", None))
        authors = [format_author(i, published_at) for i in authors_ if i]
        summary = get_summary(content_html)
        abstract = post.get("abstract", None)
        abstract = get_abstract(summary, abstract)
        reference = await get_references(content_html)
        relationships = get_relationships(content_html)
        title = get_title(post.get("title"))
        url = normalize_url(post.get("url"), secure=blog.get("secure", True))
        archive_url = (
            blog["archive_prefix"] + url if blog.get("archive_prefix", None) else None
        )
        images = get_images(content_html, url, blog["home_page_url"])
        image = post.get("image", None) or get_image(images)

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

        # upsert post with commonmeta if it has a DOI
        if post.get("doi", None):
            id_ = id_as_str(post.get("doi"))
            await get_single_work(id_)

        return {
            "authors": authors,
            "blog_name": blog.get("title"),
            "blog_slug": blog.get("slug"),
            "content_text": content_text,
            "summary": summary,
            "abstract": abstract,
            "published_at": published_at,
            "updated_at": updated_at,
            "image": image,
            "images": images,
            "language": detect_language(content_text),
            "category": blog.get("category", None),
            "reference": reference,
            "relationships": relationships,
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


def filter_updated_posts(posts, blog, key):
    """Filter posts by date updated."""

    def parse_date(date):
        """Parse date into iso8601 string"""
        date_updated = get_date(date)
        return unix_timestamp(date_updated)

    return [x for x in posts if parse_date(x.get(key, None)) > blog["updated_at"]]


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
                    "content_text": post.get("content_text", ""),
                    "images": post.get("images", None),
                    "updated_at": post.get("updated_at", None),
                    "published_at": post.get("published_at", None),
                    "image": post.get("image", None),
                    "language": post.get("language", None),
                    "category": post.get("category", None),
                    "reference": post.get("reference", None),
                    "relationships": post.get("relationships", None),
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
        record = (
            supabase.table("posts")
            .select(postsWithContentSelect)
            .eq("guid", post.get("guid", None))
            .maybe_single()
            .execute()
        )
        guid = record.data.get("guid", None)
        invenio_id = record.data.get("invenio_id", None)
        community_id = py_.get(record.data, "blog.community_id")

        # if InvenioRDM record exists, update it, otherwise create it
        if invenio_id:
            update_record(record.data, invenio_id, community_id)
        else:
            create_record(record.data, guid, community_id)

        return post_to_update.data[0]
    except Exception as e:
        print(e)
        return None


def create_record(record, guid: str, community_id: str):
    """Create InvenioRDM record."""
    try:
        if community_id is None:
            return {"error": "Blog community not found"}

        subject = Metadata(record, via="json_feed_item")
        record = JSON.loads(subject.write(to="inveniordm"))

        # remove publisher field, currently not used with InvenioRDM
        record = py_.omit(record, "metadata.publisher")

        # validate funding, lookup award metadata if needed
        if py_.get(record, "metadata.funding"):
            record["metadata"]["funding"] = validate_funding(
                py_.get(record, "metadata.funding")
            )

        # create draft record
        url = f"{environ['QUART_INVENIORDM_API']}/api/records"
        headers = {"Authorization": f"Bearer {environ['QUART_INVENIORDM_TOKEN']}"}
        response = httpx.post(url, headers=headers, json=record, timeout=10.0)
        # return error if record was not created
        if response.status_code != 201:
            print(response.status_code, "create_draft_record")
            # print(response.json())
            return response.json()

        invenio_id = response.json()["id"]

        # publish draft record
        url = f"{environ['QUART_INVENIORDM_API']}/api/records/{invenio_id}/draft/actions/publish"
        headers = {"Authorization": f"Bearer {environ['QUART_INVENIORDM_TOKEN']}"}
        response = httpx.post(url, headers=headers, timeout=10.0)
        if response.status_code != 202:
            print(response.status_code, "publish_draft_record")
            # print(response.json())
            return response.json()

        # add draft record to blog community
        add_record_to_community(invenio_id, community_id)

        # update rogue scholar database with InvenioRDM record id (invenio_id) if record was created
        post_to_update = (
            supabase_admin.table("posts")
            .update(
                {
                    "invenio_id": invenio_id,
                }
            )
            .eq("guid", guid)
            .execute()
        )
        if len(post_to_update.data) == 0:
            print(f"error creating record invenio_id {invenio_id} for guid {guid}")

        return response
    except Exception as error:
        print(error)
        return None


def update_record(record, invenio_id: str, community_id: str):
    """Update InvenioRDM record."""
    try:
        subject = Metadata(record, via="json_feed_item")
        record = JSON.loads(subject.write(to="inveniordm"))

        # remove publisher field, currently not used with InvenioRDM
        record = py_.omit(record, "metadata.publisher")

        # validate funding, lookup award metadata if needed
        if py_.get(record, "metadata.funding"):
            record["metadata"]["funding"] = validate_funding(
                py_.get(record, "metadata.funding")
            )

        # create draft record from published record
        url = f"{environ['QUART_INVENIORDM_API']}/api/records/{invenio_id}/draft"
        headers = {"Authorization": f"Bearer {environ['QUART_INVENIORDM_TOKEN']}"}
        response = httpx.post(url, headers=headers, timeout=10.0)
        if response.status_code != 201:
            print(response.status_code, "u create_draft_record")
            # print(response.json())
            return response.json()

        # update draft record
        url = f"{environ['QUART_INVENIORDM_API']}/api/records/{invenio_id}/draft"
        headers = {"Authorization": f"Bearer {environ['QUART_INVENIORDM_TOKEN']}"}
        response = httpx.put(url, headers=headers, json=record, timeout=10.0)
        if response.status_code != 200:
            print(response.status_code, "u update_draft_record")
            # print(response.json())
            return response.json()

        # publish draft record
        url = f"{environ['QUART_INVENIORDM_API']}/api/records/{invenio_id}/draft/actions/publish"
        headers = {"Authorization": f"Bearer {environ['QUART_INVENIORDM_TOKEN']}"}
        response = httpx.post(url, headers=headers, timeout=10.0)
        if response.status_code != 202:
            print(response.status_code, "u publish_draft_record")
            # print(response.json())
            return response.json()

        # add draft record to blog community if not already added
        communities = py_.get(response.json(), "parent.communities.entries", [])
        if len(communities) == 0:
            add_record_to_community(invenio_id, community_id)

        return response
    except Exception as error:
        print(error)
        return None


def add_record_to_community(invenio_id: str, community_id: str):
    """Add record to community."""
    try:
        data = {
            "communities": [
                {"id": community_id},
            ]
        }
        url = f"{environ['QUART_INVENIORDM_API']}/api/records/{invenio_id}/communities"
        headers = {"Authorization": f"Bearer {environ['QUART_INVENIORDM_TOKEN']}"}
        response = httpx.post(url, headers=headers, json=data, timeout=10.0)
        if response.status_code != 201:
            print(response.json())
        return response
    except Exception as error:
        print(error)
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


async def get_references(content_html: str):
    """Extract references from content_html,
    defined as the text after the tag "References</h2>",
    "References</h3>" or "References</h4>. Store them in works table."""

    reference_html = re.split(
        r"(?:References|Referenzen|Bibliography)<\/(?:h1|h2|h3|h4)>",
        content_html,
        maxsplit=2,
    )
    if len(reference_html) == 1:
        return []

    # strip optional text after references, using <hr>, <hr />, <h2, <h3, <h4 as tag
    reference_html[1] = re.split(
        r"(?:<hr \/>|<hr>|<h2|<h3|<h4)", reference_html[1], maxsplit=2
    )[0]

    urls = get_urls(reference_html[1])
    if not urls or len(urls) == 0:
        return []

    tasks = []
    for index, url in enumerate(urls):
        task = format_reference(url, index)
        tasks.append(task)

    formatted_references = py_.compact(await asyncio.gather(*tasks))
    return formatted_references


async def format_reference(url, index):
    """Format reference."""
    if validate_url(normalize_id(url)) in ["DOI", "URL"]:
        id_ = normalize_id(url)
        work = await get_single_work(id_as_str(id_))
        if work is not None:
            identifier = py_.get(work, "id", None)
            title = py_.get(work, "titles.0.title", None)
            publication_year = py_.get(work, "date.published", None)
        else:
            identifier = id_
            title = None
            publication_year = None
        return compact(
            {
                "key": f"ref{index + 1}",
                "id": identifier,
                "title": title,
                "publicationYear": publication_year[:4] if publication_year else None,
            }
        )
    else:
        return {
            "key": f"ref{index + 1}",
            "id": url,
        }


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
    if abstract is None:
        return None
    le = min(len(abstract), 100)
    rat = ratio(summary[:le], abstract[:le])
    return abstract if rat <= 0.75 else None


def get_relationships(content_html: str):
    """Get relationships from content_html. Extract links from
    Acknowledgments section,defined as the text after the tag
    "Acknowledgments</h2>", "Acknowledgments</h3>" or "Acknowledgments</h4>"""

    try:
        relationships_html = re.split(
            r"Acknowledgments<\/(?:h1|h2|h3|h4)>",
            content_html,
            maxsplit=2,
        )
        if len(relationships_html) == 1:
            return []

        # strip optional text after notes, using <hr>, <hr />, <h2, <h3, <h4 as tag
        relationships_html[1] = re.split(
            r"(?:<hr \/>|<hr>|<h2|<h3|<h4)", relationships_html[1], maxsplit=2
        )[0]

        # split notes into sentences and classify relationship type for each sentence
        sentences = re.split(r"(?<=\w{3}[.!?;])\s+", relationships_html[1])

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
            if _type is None:
                return None
            return {"type": _type, "urls": urls}

        relationships = [extract_url(i) for i in sentences]
        return [i for i in relationships if i is not None]
    except Exception as e:
        print(e)
        return []


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
            if validate_doi(url):
                f = furl(url)
                if f.scheme == "http":
                    f.scheme = "https"
                if f.host == "dx.doi.org":
                    f.host = "doi.org"
                url = f.url
            else:
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
            return None
        if not item.get("award", None).get("number", None):
            return None
        award = get_award(item.get("award", None).get("number", None))
        if not award:
            return py_.omit(item, "award")
        item["award"] = award
        return item

    return [format_funding(i) for i in funding]


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
