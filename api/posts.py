"""Posts module."""
from os import environ
from furl import furl
import aiohttp
import asyncio
import requests
import re
import pydash as py_
import nh3
import html
import json as jsn
import xmltodict
import time
import traceback
from urllib.parse import unquote
from commonmeta import validate_doi, normalize_doi, validate_url
from Levenshtein import ratio

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
)
from api.supabase import (
    supabase_admin_client as supabase_admin,
    supabase_client as supabase,
)
from api.typesense import typesense_client as typesense


async def extract_all_posts(page: int = 1, update_all: bool = False):
    """Extract all posts."""

    blogs = (
        supabase.table("blogs")
        .select("slug")
        .in_("status", ["active"])
        .order("title", desc=False)
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


async def update_posts(posts: list):
    """Update posts."""

    try:

        def update_post(post):
            id_ = py_.get(post, "document.id")
            if len(id_) == 5:
                print(id_, py_.get(post, "document.doi", None))
                typesense.collections["posts"].documents[id_].delete()
                return {}
            return py_.get(post, "document.content_text", "")

        return [update_post(x) for x in posts]
    except Exception:
        print(traceback.format_exc())
        return {}


async def extract_all_posts_by_blog(slug: str, page: int = 1, update_all: bool = False):
    """Extract all posts by blog."""

    try:
        response = (
            supabase.table("blogs")
            .select(
                "id, slug, feed_url, current_feed_url, home_page_url, archive_prefix, feed_format, created_at, updated_at, mastodon, generator, generator_raw, language, category, favicon, title, description, category, status, user_id, authors, plan, use_api, relative_url, filter, secure"
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
        # limit number of pages for free plan to 5 (50 posts)
        page = min(page, 5) if blog.get("plan", None) == "Starter" else page
        start_page = (page - 1) * 50 if page > 0 else 0
        end_page = (page - 1) * 50 + 50 if page > 0 else 50

        # handle pagination depending on blogging platform and whether we use their API
        match generator:
            case "WordPress":
                if blog.get("use_api", False):
                    url = furl(blog.get("home_page_url", None))
                    params = {
                        "rest_route": "/wp/v2/posts",
                        "page": page,
                        "per_page": 50,
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
                    params = {"page": page, "number": 50}
                else:
                    params = {"paged": page}
            case "Ghost":
                if blog.get("use_api", False):
                    host = environ[f"QUART_{blog.get('slug').upper()}_GHOST_API_HOST"]
                    key = environ[f"QUART_{blog.get('slug').upper()}_GHOST_API_KEY"]
                    url = url.set(host=host, path="/ghost/api/content/posts/")
                    params = {
                        "page": page,
                        "limit": 50,
                        "filter": blog.get("filter", None) or "visibility:public",
                        "include": "tags,authors",
                        "key": key,
                    }
                else:
                    params = {}
            case "Blogger":
                params = {"start-index": start_page + 1, "max-results": 50}
            case "Substack":
                url = url.set(path="/api/v1/posts/")
                params = {"sort": "new", "offset": start_page, "limit": 50}
            case _:
                params = {}

        feed_url = url.set(params).url
        blog_with_posts = {}

        # use pagination of results only for non-API blogs
        if params:
            start_page = 0
            end_page = 50

        if generator == "Substack":
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    feed_url, timeout=30, raise_for_status=True
                ) as resp:
                    posts = await resp.json()
                    # only include posts that have been modified since last update
                    if not update_all:
                        posts = filter_updated_posts(posts, blog, key="post_date")
                    extract_posts = [extract_substack_post(x, blog) for x in posts]
            blog_with_posts["entries"] = await asyncio.gather(*extract_posts)
        elif generator == "WordPress" and blog["use_api"]:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    feed_url, timeout=30, raise_for_status=True
                ) as resp:
                    posts = await resp.json()
                    if not update_all:
                        posts = filter_updated_posts(posts, blog, key="modified_gmt")
                    extract_posts = [extract_wordpress_post(x, blog) for x in posts]
            blog_with_posts["entries"] = await asyncio.gather(*extract_posts)
        elif generator == "WordPress.com" and blog["use_api"]:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    feed_url, timeout=30, raise_for_status=True
                ) as resp:
                    json = await resp.json()
                    posts = json.get("posts", [])
                    if not update_all:
                        posts = filter_updated_posts(posts, blog, key="modified")
                    extract_posts = [extract_wordpresscom_post(x, blog) for x in posts]
            blog_with_posts["entries"] = await asyncio.gather(*extract_posts)
        elif generator == "Ghost" and blog["use_api"]:
            headers = {"Accept-Version": "v5.0"}
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    feed_url, headers=headers, timeout=30, raise_for_status=True
                ) as resp:
                    json = await resp.json()
                    posts = json.get("posts", [])
                    if not update_all:
                        posts = filter_updated_posts(posts, blog, key="updated_at")
                    extract_posts = [extract_ghost_post(x, blog) for x in posts]
            blog_with_posts["entries"] = await asyncio.gather(*extract_posts)
        elif blog["feed_format"] == "application/feed+json":
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    feed_url, timeout=30, raise_for_status=True
                ) as resp:
                    json = await resp.json()
                    posts = json.get("items", [])
                    if not update_all:
                        posts = filter_updated_posts(posts, blog, key="date_modified")
                    posts = posts[start_page:end_page]
            extract_posts = [extract_json_feed_post(x, blog) for x in posts]
            blog_with_posts["entries"] = await asyncio.gather(*extract_posts)
        elif blog["feed_format"] == "application/atom+xml":
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    feed_url, timeout=30, raise_for_status=True
                ) as resp:
                    # fix malformed xml
                    xml = fix_xml(await resp.read())
                    json = xmltodict.parse(
                        xml, dict_constructor=dict, force_list={"entry"}
                    )
                    posts = py_.get(json, "feed.entry", [])
                    if not update_all:
                        posts = filter_updated_posts(posts, blog, key="published")
                    posts = posts[start_page:end_page]
            extract_posts = [
                extract_atom_post(jsn.loads(jsn.dumps(x)), blog) for x in posts
            ]
            blog_with_posts["entries"] = await asyncio.gather(*extract_posts)
        elif blog["feed_format"] == "application/rss+xml":
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    feed_url, timeout=30, raise_for_status=True
                ) as resp:
                    # fix malformed xml
                    xml = fix_xml(await resp.read())
                    json = xmltodict.parse(
                        xml, dict_constructor=dict, force_list={"category", "item"}
                    )
                    posts = py_.get(json, "rss.channel.item", [])
                    if not update_all:
                        posts = filter_updated_posts(posts, blog, key="pubDate")
                    if blog.get("filter", None):
                        posts = filter_posts(posts, blog, key="category")
                    posts = posts[start_page:end_page]
            extract_posts = [
                extract_rss_post(jsn.loads(jsn.dumps(x)), blog) for x in posts
            ]
            blog_with_posts["entries"] = await asyncio.gather(*extract_posts)
        else:
            blog_with_posts["entries"] = []
        if blog.get("status", None) != "active":
            return blog_with_posts["entries"]
        return [upsert_single_post(i) for i in blog_with_posts["entries"]]
    except TimeoutError:
        print(f"Timeout error in blog {blog['slug']}.")
        return []
    except Exception as e:
        print(f"{e} error in blog {blog['slug']}.")
        print(traceback.format_exc())
        return []


async def extract_wordpress_post(post, blog):
    """Extract WordPress post from REST API."""

    try:

        def format_author(author):
            """Format author. Optionally lookup real name from username,
            and ORCID from name. Ideally this is done in the Wordpress
            user settings."""

            return normalize_author(author.get("name", None), author.get("url", None))

        # use default author for blog if no post author found
        authors_ = wrap(py_.get(post, "_embedded.author", None))
        if len(authors_) == 0 or authors_[0].get("name", None) is None:
            authors_ = wrap(blog.get("authors", None))
        authors = [format_author(i) for i in authors_]
        content_html = py_.get(post, "content.rendered", "")
        content_text = get_markdown(content_html)
        summary = get_summary(content_html)
        abstract = get_summary(py_.get(post, "excerpt.rendered", ""))
        abstract = get_abstract(summary, abstract)
        reference = get_references(content_html)
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
        )
        if not image and len(images) > 0 and int(images[0].get("width", 200)) >= 200:
            image = images[0].get("src", None)

        # optionally remove category that is used to filter posts
        if blog.get("filter", None):
            cat = blog.get("filter", "").split(":")[1]
            categories = [normalize_tag(i.get("name", None)) for i in wrap(py_.get(post, "_embedded.wp:term.0", None)) if i.get("id", None) != int(cat)]
        else:
            categories = [
            normalize_tag(i.get("name", None))
                for i in wrap(py_.get(post, "_embedded.wp:term.0", None))
            ]
        tags = [
            normalize_tag(i.get("name", None))
            for i in wrap(py_.get(post, "_embedded.wp:term.1", None))
        ]
        terms = categories + tags
        terms = py_.uniq(terms)[:5]
        print(terms)
        return {
            "authors": authors,
            "blog_name": blog.get("title", None),
            "blog_slug": blog.get("slug", None),
            "content_text": content_text,
            "summary": summary,
            "abstract": abstract,
            "published_at": unix_timestamp(post.get("date_gmt", None)),
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
        }
    except Exception:
        print(blog.get("slug", None), traceback.format_exc())
        return {}


async def extract_wordpresscom_post(post, blog):
    """Extract WordPress.com post from REST API."""
    try:

        def format_author(author):
            """Format author. Optionally lookup real name from username,
            and ORCID from name. Ideally this is done in the Wordpress
            user settings."""

            return normalize_author(author.get("name", None), author.get("URL", None))

        authors = [format_author(i) for i in wrap(post.get("author", None))]
        content_html = post.get("content", "")
        content_text = get_markdown(content_html)
        summary = get_summary(post.get("content", ""))
        abstract = get_summary(post.get("excerpt", None))
        abstract = get_abstract(summary, abstract)
        reference = get_references(content_html)
        relationships = get_relationships(content_html)
        url = normalize_url(post.get("URL", None), secure=blog.get("secure", True))
        archive_url = (
            blog["archive_prefix"] + url if blog.get("archive_prefix", None) else None
        )
        images = get_images(content_html, url, blog.get("home_page_url", None))
        image = None
        if len(images) > 0 and int(images[0].get("width", 200)) >= 200:
            image = images[0].get("src", None)
        tags = [normalize_tag(i) for i in post.get("categories", None).keys()][:5]

        return {
            "authors": authors,
            "blog_name": blog.get("title", None),
            "blog_slug": blog.get("slug", None),
            "content_text": content_text,
            "summary": summary,
            "abstract": abstract,
            "published_at": unix_timestamp(post.get("date", None)),
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
        }
    except Exception:
        print(blog.get("slug", None), traceback.format_exc())
        return {}


async def extract_ghost_post(post, blog):
    """Extract Ghost post from REST API."""

    try:

        def format_author(author):
            """Format author."""
            return normalize_author(
                author.get("name", None), author.get("website", None)
            )

        authors = [format_author(i) for i in wrap(post.get("authors", None))]
        content_html = post.get("html", "")
        content_text = get_markdown(content_html)

        # don't use excerpt as summary, because it's not html
        summary = get_summary(content_html)
        abstract = get_summary(post.get("excerpt", ""))
        abstract = get_abstract(summary, abstract)
        reference = get_references(content_html)
        relationships = get_relationships(content_html)
        url = normalize_url(post.get("url", None), secure=blog.get("secure", True))
        archive_url = (
            blog["archive_prefix"] + url if blog.get("archive_prefix", None) else None
        )
        images = get_images(content_html, url, blog.get("home_page_url", None))
        image = post.get("feature_image", None)
        if not image and len(images) > 0 and int(images[0].get("width", 200)) >= 200:
            image = images[0].get("src", None)
        tags = [normalize_tag(i.get("name", None)) for i in post.get("tags", None)][:5]

        return {
            "authors": authors,
            "blog_name": blog.get("title", None),
            "blog_slug": blog.get("slug", None),
            "content_text": content_text,
            "summary": summary,
            "abstract": abstract,
            "published_at": unix_timestamp(post.get("published_at", None)),
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
        }
    except Exception:
        print(blog.get("slug", None), traceback.format_exc())
        return {}


async def extract_substack_post(post, blog):
    """Extract Substack post from REST API."""

    try:

        def format_author(author):
            """Format author."""
            return normalize_author(author.get("name", None))

        authors = [format_author(i) for i in wrap(post.get("publishedBylines", None))]
        content_html = post.get("body_html", "")
        content_text = get_markdown(content_html)
        summary = get_summary(post.get("description", None))
        abstract = get_summary(content_html)
        abstract = get_abstract(summary, abstract)
        published_at = unix_timestamp(post.get("post_date", None))
        reference = get_references(content_html)
        relationships = get_relationships(content_html)
        url = normalize_url(
            post.get("canonical_url", None), secure=blog.get("secure", True)
        )
        archive_url = (
            blog["archive_prefix"] + url if blog.get("archive_prefix", None) else None
        )
        images = get_images(content_html, url, blog.get("home_page_url", None))
        image = post.get("cover_image", None)
        if not image and len(images) > 0 and int(images[0].get("width", 200)) >= 200:
            image = images[0].get("src", None)
        tags = [normalize_tag(i.get("name")) for i in wrap(post.get("postTags", None))][
            :5
        ]

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
        }
    except Exception:
        print(blog.get("slug", None), traceback.format_exc())
        return {}


async def extract_json_feed_post(post, blog):
    """Extract JSON Feed post."""

    try:

        def format_author(author):
            """Format author."""
            return normalize_author(author.get("name", None), author.get("url", None))

        # use default authors for blog if no post authors found
        authors_ = wrap(post.get("authors", None))
        if len(authors_) == 0:
            authors_ = wrap(blog.get("authors", None))
        authors = [format_author(i) for i in authors_]
        content_html = post.get("content_html", "")
        content_text = get_markdown(content_html)
        summary = get_summary(content_html)
        abstract = None
        reference = get_references(content_html)
        relationships = get_relationships(content_html)
        url = normalize_url(post.get("url", None), secure=blog.get("secure", True))
        archive_url = (
            blog["archive_prefix"] + url if blog.get("archive_prefix", None) else None
        )
        base_url = url
        if blog.get("relative_url", None) == "blog":
            base_url = blog.get("home_page_url", None)
        images = get_images(content_html, base_url, blog.get("home_page_url", None))
        image = py_.get(post, "media:thumbnail.@url", None)
        if not image and len(images) > 0 and int(images[0].get("width", 200)) >= 200:
            image = images[0].get("src", None)
        tags = [normalize_tag(i) for i in wrap(post.get("tags", None))][:5]

        return {
            "authors": authors,
            "blog_name": blog.get("title", None),
            "blog_slug": blog.get("slug", None),
            "content_text": content_text,
            "summary": summary,
            "abstract": abstract,
            "published_at": unix_timestamp(post.get("date_published", None)),
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
        }
    except Exception:
        print(blog.get("slug", None), traceback.format_exc())
        return {}


async def extract_atom_post(post, blog):
    """Extract Atom post."""

    try:

        def format_author(author):
            """Format author."""
            return normalize_author(author.get("name", None), author.get("uri", None))

        # use default authors for blog if no post authors found
        authors_ = wrap(post.get("author", None))
        if len(authors_) == 0 or authors_[0].get("name", None) is None:
            authors_ = wrap(blog.get("authors", None))
        authors = [format_author(i) for i in authors_]

        # workaround, as content should be encodes as CDATA block
        content_html = html.unescape(py_.get(post, "content.#text", ""))
        content_text = get_markdown(content_html)
        title = get_title(py_.get(post, "title.#text", None)) or get_title(
            post.get("title", None)
        )
        summary = get_summary(content_html)
        abstract = None
        reference = get_references(content_html)
        relationships = get_relationships(content_html)
        published_at = get_date(post.get("published", None))
        updated_at = get_date(post.get("updated", None))

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
        image = py_.get(post, "media:thumbnail.@url", None)
        # workaround for eve blog
        if image is not None:
            f = furl(image)
            if f.host == "eve.gd":
                image = unquote(image)
                if f.path.segments[0] != "images":
                    image = f.set(path="/images/" + f.path.segments[0]).url
        if not image and len(images) > 0 and int(images[0].get("width", 200)) >= 200:
            image = images[0].get("src", None)
        tags = [
            normalize_tag(i.get("@term", None))
            for i in wrap(post.get("category", None))
        ][:5]

        return {
            "authors": authors,
            "blog_name": blog.get("title", None),
            "blog_slug": blog.get("slug", None),
            "content_text": content_text,
            "summary": summary,
            "abstract": abstract,
            "published_at": unix_timestamp(published_at),
            "updated_at": unix_timestamp(updated_at or published_at),
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
        }
    except Exception:
        print(blog.get("slug", None), traceback.format_exc())
        return {}


async def extract_rss_post(post, blog):
    """Extract RSS post."""

    try:

        def format_author(author):
            """Format author."""
            return normalize_author(author.get("name", None), author.get("url", None))

        # use default author for blog if no post author found
        author = post.get("dc:creator", None) or post.get("author", None)
        if author:
            authors_ = [{"name": author}]
        else:
            authors_ = wrap(blog.get("authors", None))
        authors = [format_author(i) for i in authors_]
        content_html = py_.get(post, "content:encoded", None) or post.get(
            "description", ""
        )
        content_text = get_markdown(content_html)
        summary = get_summary(content_html) or ""
        abstract = None
        reference = get_references(content_html)
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
        published_at = get_date(post.get("pubDate", None))
        images = get_images(content_html, base_url, blog.get("home_page_url", None))
        image = py_.get(post, "media:content.@url", None) or py_.get(
            post, "media:thumbnail.@url", None
        )
        if (
            not image
            and len(images) > 0
            and int(images[0].get("width", 200)) >= 200
            and furl(images[0].get("src", None)).host not in ["latex.codecogs.com"]
        ):
            image = images[0].get("src", None)
        tags = [normalize_tag(i) for i in wrap(post.get("category", None))][:5]

        return {
            "authors": authors,
            "blog_name": blog.get("title", None),
            "blog_slug": blog.get("slug", None),
            "content_text": content_text,
            "summary": summary,
            "abstract": abstract,
            "published_at": unix_timestamp(published_at),
            "updated_at": unix_timestamp(published_at),
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
    filters = blog.get("filter", "").split(":")
    if len(filters) != 2 or filters[0] != key:
        return posts
    filters = filters[1].split(",")

    return [x for x in posts if x.get(key, None) in filters]


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
        return post_to_update.data[0]
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


def get_references(content_html: str):
    """Extract references from content_html,
    defined as the text after the tag "References</h2>",
    "References</h3>" or "References</h4>"""

    try:
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

        def format_reference(url, index):
            """Format reference."""
            if validate_url(url) == "DOI":
                doi = normalize_doi(url)
                response = requests.get(
                    doi,
                    headers={"Accept": "application/vnd.citationstyles.csl+json"},
                    timeout=10,
                )
                if response.status_code not in [200, 301, 302]:
                    return None
                csl = response.json()
                publication_year = py_.get(csl, "issued.date-parts.0.0", None)
                return compact(
                    {
                        "key": f"ref{index + 1}",
                        "doi": doi,
                        "title": csl.get("title", None),
                        "publicationYear": str(publication_year)
                        if publication_year
                        else None,
                    }
                )
            elif validate_url(url) == "URL":
                response = requests.head(url, timeout=10)
                # check that URL resolves.
                # TODO: check for redirects
                if response.status_code in [404]:
                    return None
                return {
                    "key": f"ref{index + 1}",
                    "url": url,
                }
            else:
                return None

        references = [format_reference(url, index) for index, url in enumerate(urls)]
        return references
    except Exception as e:
        print(e)
        return []


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


def get_summary(content_html: str = None, maxlen: int = 450):
    """Get summary from excerpt or content_html."""
    if not content_html:
        return None
    content_html = re.sub(r"(<br>|<br/>|<p>|</pr>)", " ", content_html)
    content_html = re.sub(r"(h1>|h2>|h3>|h4>)", "strong> ", content_html)
    sanitized = nh3.clean(
        content_html,
        tags={"b", "i", "em", "strong", "sub", "sup"},
        clean_content_tags={"figcaption"},
        attributes={},
    )
    sanitized = re.sub(r"\n+", " ", sanitized).strip()
    truncated = py_.truncate(sanitized, maxlen, omission="", separator=" ")

    # remove incomplete last sentence
    if truncated[-1] not in [".", "!", "?", ";"]:
        sentences = re.split(r"(?<=\w{3}[.!?;])\s+", truncated)
        if len(sentences) > 1:
            truncated = " ".join(sentences[:-1])
        else:
            truncated = sentences[0]

    # make sure html tags are closed and trailing whitespace is removed
    soup = get_soup(truncated)
    string = soup.prettify()
    return string.strip()


def get_abstract(summary: str, abstract: str):
    """Get abstract if not beginning of post.
    Use Levenshtein distance to compare summary and abstract."""
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
            type_ = None
            if re.search("(originally published|cross-posted)", sentence):
                type_ = "IsIdenticalTo"
            elif re.search("peer-reviewed version", sentence):
                type_ = "IsPreprintOf"
            elif re.search("work was funded", sentence):
                type_ = "HasAward"
            if type_ is None:
                return None
            return {"type": type_, "url": urls[0]}

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
