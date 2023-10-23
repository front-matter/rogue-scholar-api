"""Posts module."""
from os import environ
from furl import furl
import aiohttp
import asyncio
from bs4 import BeautifulSoup
import re
import pydash as py_
import nh3
import html
import json as jsn
import xmltodict
import time
from idutils import is_doi, is_orcid
from commonmeta.base_utils import wrap, compact

from rogue_scholar_api.utils import (
    unix_timestamp,
    normalize_tag,
    get_date,
    normalize_url,
    AUTHOR_IDS,
)
from rogue_scholar_api.supabase import (
    supabase_admin_client as supabase_admin,
    supabase_client as supabase,
)


def author_ids():
    """Author ids that can't be extracted from the blogging platform, e.g. from an RSS feed."""


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


async def extract_all_posts_by_blog(slug: str, page: int = 1, update_all: bool = False):
    """Extract all posts by blog."""

    response = (
        supabase.table("blogs")
        .select(
            "id, slug, feed_url, current_feed_url, home_page_url, archive_prefix, feed_format, created_at, updated_at, use_mastodon, generator, language, favicon, title, description, category, status, user_id, authors, plan, use_api, relative_url, filter"
        )
        .eq("slug", slug)
        .maybe_single()
        .execute()
    )
    blog = response.data
    if not blog:
        return {}
    url = furl(blog.get("feed_url", None))
    generator = (
        blog.get("generator", "").split(" ")[0] if blog.get("generator", None) else None
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

            else:
                params = {"paged": page}
        case "WordPress.com":
            if blog.get("use_api", False):
                site = furl(blog.get("home_page_url", None)).host
                url = url.set(
                    host="public-api.wordpress.com",
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

    try:
        if generator == "Substack":
            async with aiohttp.ClientSession() as session:
                async with session.get(feed_url, timeout=10) as resp:
                    posts = await resp.json()
                    # only include posts that have been modified since last update
                    if not update_all:
                        posts = filter_updated_posts(posts, blog, key="post_date")
                    extract_posts = [extract_substack_post(x, blog) for x in posts]
            blog_with_posts["entries"] = await asyncio.gather(*extract_posts)
        elif generator == "WordPress" and blog["use_api"]:
            async with aiohttp.ClientSession() as session:
                async with session.get(feed_url, timeout=10) as resp:
                    posts = await resp.json()
                    if not update_all:
                        posts = filter_updated_posts(posts, blog, key="modified_gmt")
                    extract_posts = [extract_wordpress_post(x, blog) for x in posts]
            blog_with_posts["entries"] = await asyncio.gather(*extract_posts)
        elif generator == "WordPress.com" and blog["use_api"]:
            async with aiohttp.ClientSession() as session:
                async with session.get(feed_url, timeout=10) as resp:
                    json = await resp.json()
                    posts = json.get("posts", [])
                    if not update_all:
                        posts = filter_updated_posts(posts, blog, key="modified")
                    extract_posts = [extract_wordpresscom_post(x, blog) for x in posts]
            blog_with_posts["entries"] = await asyncio.gather(*extract_posts)
        elif generator == "Ghost" and blog["use_api"]:
            headers = {"Accept-Version": "v5.0"}
            async with aiohttp.ClientSession() as session:
                async with session.get(feed_url, headers=headers, timeout=10) as resp:
                    json = await resp.json()
                    posts = json.get("posts", [])
                    if not update_all:
                        posts = filter_updated_posts(posts, blog, key="updated_at")
                    extract_posts = [extract_ghost_post(x, blog) for x in posts]
            blog_with_posts["entries"] = await asyncio.gather(*extract_posts)
        elif blog["feed_format"] == "application/feed+json":
            async with aiohttp.ClientSession() as session:
                async with session.get(feed_url, timeout=10) as resp:
                    json = await resp.json()
                    posts = json.get("items", [])
                    if not update_all:
                        posts = filter_updated_posts(posts, blog, key="date_modified")
                    posts = posts[start_page:end_page]
            extract_posts = [extract_json_feed_post(x, blog) for x in posts]
            blog_with_posts["entries"] = await asyncio.gather(*extract_posts)
        elif blog["feed_format"] == "application/atom+xml":
            async with aiohttp.ClientSession() as session:
                async with session.get(feed_url, timeout=10) as resp:
                    xml = await resp.text()
                    json = xmltodict.parse(xml)
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
                async with session.get(feed_url, timeout=10) as resp:
                    xml = await resp.text()
                    json = xmltodict.parse(xml)
                    posts = py_.get(json, "rss.channel.item", [])
                    if not update_all:
                        posts = filter_updated_posts(posts, blog, key="pubDate")
                    posts = posts[start_page:end_page]
            extract_posts = [
                extract_rss_post(jsn.loads(jsn.dumps(x)), blog) for x in posts
            ]
            blog_with_posts["entries"] = await asyncio.gather(*extract_posts)
        else:
            blog_with_posts["entries"] = []
    except Exception as e:
        print(e)
        blog_with_posts["entries"] = []

    return [upsert_single_post(i) for i in blog_with_posts["entries"]]


async def extract_wordpress_post(post, blog):
    """Extract WordPress post from REST API."""

    def format_author(author):
        """Format author."""
        name = author.get("name", None)
        url = author.get("url", None)

        # set full name and homepage url in WordPress user profile
        # fallback for specific users here
        if name == "davidshotton":
            name = "David M. Shotton"
            url = "https://orcid.org/0000-0001-5506-523X"
        elif name == "meineckei":
            name = "Isabella Meinecke"
        elif name == "schradera":
            name = "Antonia Schrader"
        elif name == "arningu":
            name = "Ursula Arning"
        elif name == "rmounce":
            name = "Ross Mounce"
        return compact(
            {
                "name": name,
                "url": url if url else None,
            }
        )

    # use default author for blog if no post author found
    # if not author"name"] && blog.authors) {
    #     author = blog.authors && blog.authors[0]
    authors = [format_author(i) for i in wrap(py_.get(post, "_embedded.author", None))]
    content_html = py_.get(post, "content.rendered", "")
    soup = BeautifulSoup(content_html, "html.parser")
    reference = get_references(content_html)
    relationships = get_relationships(content_html)
    url = normalize_url(post.get("link", None), secure=True)
    images = get_images(soup, url, blog["home_page_url"])
    image = (
        py_.get(post, "_embedded.wp:featuredmedia[0].source_url", None)
        or py_.get(post, "yoast_head_json.og_image[0].url", None)
        or post.get("jetpack_featured_media_url", None)
    )
    if not image and len(images) > 0:
        image = images[0].get("src", None)
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

    return {
        "authors": authors,
        "blog_id": blog.get("id", None),
        "blog_name": blog.get("title", None),
        "blog_slug": blog.get("slug", None),
        "content_html": content_html,
        "summary": get_abstract(content_html),
        "published_at": unix_timestamp(post.get("date_gmt", None)),
        "updated_at": unix_timestamp(post.get("modified_gmt", None)),
        "image": image,
        "images": images,
        "language": blog.get("language", "en"),
        "reference": reference,
        "relationships": relationships,
        "tags": terms,
        "title": py_.get(post, "title.rendered", ""),
        "url": url,
    }


async def extract_wordpresscom_post(post, blog):
    """Extract WordPress.com post from REST API."""

    def format_author(author):
        """Format author."""
        url = author.get("URL", None)
        return compact(
            {
                "name": author.get("name", None),
                "url": url if url else None,
            }
        )

    authors = [format_author(i) for i in wrap(post.get("author", None))]
    content_html = post.get("content", "")
    soup = BeautifulSoup(content_html, "html.parser")
    summary = get_abstract(post.get("excerpt", None)) or get_title(
        post.get("title", None)
    )
    reference = get_references(content_html)
    relationships = get_relationships(content_html)
    url = normalize_url(post.get("URL", None), secure=True)
    images = get_images(soup, url, blog.get("home_page_url", None))
    image = images[0].get("src", None) if len(images) > 0 else None
    tags = [normalize_tag(i) for i in post.get("categories", None).keys()][:5]

    return {
        "authors": authors,
        "blog_id": blog.get("id", None),
        "blog_name": blog.get("title", None),
        "blog_slug": blog.get("slug", None),
        "content_html": content_html,
        "summary": summary,
        "published_at": unix_timestamp(post.get("date", None)),
        "updated_at": unix_timestamp(post.get("modified", None)),
        "image": image,
        "images": images,
        "language": blog.get("language", "en"),
        "reference": reference,
        "relationships": relationships,
        "tags": tags,
        "title": get_title(post.get("title", None)),
        "url": url,
    }


async def extract_ghost_post(post, blog):
    """Extract Ghost post from REST API."""

    def format_author(author):
        """Format author."""
        return compact(
            {
                "name": author.get("name", None),
                "url": author.get("website", None),
            }
        )

    authors = [format_author(i) for i in wrap(post.get("authors", None))]
    content_html = post.get("html", "")
    soup = BeautifulSoup(content_html, "html.parser")
    summary = get_abstract(post.get("excerpt", None))
    if not summary:
        summary = get_abstract(content_html)
    reference = get_references(content_html)
    relationships = get_relationships(content_html)
    url = normalize_url(post.get("url", None), secure=True)
    images = get_images(soup, url, blog.get("home_page_url", None))
    image = post.get("feature_image", None)
    if not image and len(images) > 0:
        image = images[0].get("src", None)
    tags = [normalize_tag(i.get("name", None)) for i in post.get("tags", None)][:5]

    return {
        "authors": authors,
        "blog_id": blog.get("id", None),
        "blog_name": blog.get("title", None),
        "blog_slug": blog.get("slug", None),
        "content_html": content_html,
        "summary": summary,
        "published_at": unix_timestamp(post.get("published_at", None)),
        "updated_at": unix_timestamp(post.get("updated_at", None)),
        "image": image,
        "images": images,
        "language": blog.get("language", "en"),
        "reference": reference,
        "relationships": relationships,
        "tags": tags,
        "title": get_title(post.get("title", None)),
        "url": url,
    }


async def extract_substack_post(post, blog):
    """Extract Substack post from REST API."""

    def format_author(author):
        """Format author."""
        name = author.get("name", None)
        return compact(
            {
                "name": name,
                "url": AUTHOR_IDS.get(name, None),
            }
        )

    authors = [format_author(i) for i in wrap(post.get("publishedBylines", None))]
    content_html = post.get("body_html", "")
    soup = BeautifulSoup(content_html, "html.parser")
    summary = get_abstract(post.get("description", None))
    published_at = unix_timestamp(post.get("post_date", None))
    reference = get_references(content_html)
    relationships = get_relationships(content_html)
    url = normalize_url(post.get("canonical_url", None), secure=True)
    images = get_images(soup, url, blog.get("home_page_url", None))
    image = post.get("cover_image", None)
    if not image and len(images) > 0:
        image = images[0].get("src", None)
    tags = [normalize_tag(i.get("name")) for i in wrap(post.get("postTags", None))][:5]

    return {
        "authors": authors,
        "blog_id": blog.get("id", None),
        "blog_name": blog.get("title", None),
        "blog_slug": blog.get("slug", None),
        "content_html": content_html,
        "summary": summary,
        "published_at": published_at,
        "updated_at": published_at,
        "image": image,
        "images": images,
        "language": blog.get("language", "en"),
        "reference": reference,
        "relationships": relationships,
        "tags": tags,
        "title": get_title(post.get("title", None)),
        "url": url,
    }


async def extract_json_feed_post(post, blog):
    """Extract JSON Feed post."""

    def format_author(author):
        """Format author."""
        name = author.get("name", None)
        uri = author.get("url", None)
        url = uri if uri and is_orcid(uri) else AUTHOR_IDS.get(name, None)
        return compact({"name": name, "url": url})

    authors = [format_author(i) for i in wrap(post.get("authors", None))]
    content_html = post.get("content_html", "")
    soup = BeautifulSoup(content_html, "html.parser")
    summary = get_abstract(content_html)
    reference = get_references(content_html)
    relationships = get_relationships(content_html)
    url = normalize_url(post.get("url", None), secure=True)
    images = get_images(soup, url, blog.get("home_page_url", None))
    image = py_.get(post, "media:thumbnail.@url", None)
    if not image and len(images) > 0:
        image = images[0].get("src", None)
    tags = [normalize_tag(i) for i in wrap(post.get("tags", None))][:5]

    return {
        "authors": authors,
        "blog_id": blog.get("id", None),
        "blog_name": blog.get("title", None),
        "blog_slug": blog.get("slug", None),
        "content_html": content_html,
        "summary": summary,
        "published_at": unix_timestamp(post.get("date_published", None)),
        "updated_at": unix_timestamp(post.get("date_modified", None)),
        "image": image,
        "images": images,
        "language": blog.get("language", "en"),
        "reference": reference,
        "relationships": relationships,
        "tags": tags,
        "title": get_title(post.get("title", None)),
        "url": url,
    }


async def extract_atom_post(post, blog):
    """Extract Atom post."""

    def format_author(author):
        """Format author."""
        name = author.get("name", None)
        uri = author.get("uri", None)
        url = uri if uri and is_orcid(uri) else AUTHOR_IDS.get(name, None)
        return compact(
            {
                "name": name,
                "url": url,
            }
        )

    authors = [format_author(i) for i in wrap(post.get("author", None))]
    content_html = py_.get(post, "content.#text", "")
    soup = BeautifulSoup(content_html, "html.parser")
    summary = get_abstract(content_html)
    reference = get_references(content_html)
    relationships = get_relationships(content_html)
    published_at = get_date(post.get("published", None))
    updated_at = get_date(post.get("updated", None))

    def get_url(links):
        """Get url."""
        return normalize_url(
            next(
                (link["@href"] for link in wrap(links) if link["@type"] == "text/html"),
                None,
            ),
            secure=True,
        )

    url = get_url(post.get("link", None))
    images = get_images(soup, url, blog.get("home_page_url", None))
    image = py_.get(post, "media:thumbnail.@url", None)
    if not image and len(images) > 0:
        image = images[0].get("src", None)
    tags = [
        normalize_tag(i.get("@term", None)) for i in wrap(post.get("category", None))
    ][:5]

    return {
        "authors": authors,
        "blog_id": blog.get("id", None),
        "blog_name": blog.get("title", None),
        "blog_slug": blog.get("slug", None),
        "content_html": content_html,
        "summary": summary,
        "published_at": unix_timestamp(published_at),
        "updated_at": unix_timestamp(updated_at or published_at),
        "image": image,
        "images": images,
        "language": blog.get("language", "en"),
        "reference": reference,
        "relationships": relationships,
        "tags": tags,
        "title": get_title(py_.get(post, "title.#text", "")),
        "url": url,
    }


async def extract_rss_post(post, blog):
    """Extract RSS post."""

    def format_author(author):
        """Format author."""
        return compact(
            {
                "name": author,
                "url": AUTHOR_IDS.get(author, None),
            }
        )

    authors = [format_author(i) for i in wrap(post.get("dc:creator", None))]
    content_html = post.get("description", "")
    soup = BeautifulSoup(content_html, "html.parser")
    summary = get_abstract(content_html)
    reference = get_references(content_html)
    relationships = get_relationships(content_html)
    url = normalize_url(post.get("link", None), secure=True)
    published_at = get_date(post.get("pubDate", None))
    images = get_images(soup, url, blog.get("home_page_url", None))
    image = py_.get(post, "media:content.@url", None) or py_.get(
        post, "media:thumbnail.@url", None
    )
    # if not image and len(images) > 0:
    #     image = images[0].get("src", None)
    tags = [normalize_tag(i) for i in wrap(post.get("category", None))][:5]

    return {
        "authors": authors,
        "blog_id": blog.get("id", None),
        "blog_name": blog.get("title", None),
        "blog_slug": blog.get("slug", None),
        "content_html": content_html,
        "summary": summary,
        "published_at": unix_timestamp(published_at),
        "updated_at": unix_timestamp(published_at),
        "image": image,
        "images": images,
        "language": blog.get("language", "en"),
        "reference": reference,
        "relationships": relationships,
        "tags": tags,
        "title": get_title(post.get("title", None)),
        "url": url,
    }


def filter_updated_posts(posts, blog, key):
    """Filter posts by date updated."""

    def parse_date(date):
        """Parse date into iso8601 string"""
        date_updated = get_date(date)
        return unix_timestamp(date_updated)

    return [x for x in posts if parse_date(x.get(key, None)) > blog["updated_at"]]


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
                    "blog_id": post.get("blog_id", None),
                    "blog_name": post.get("blog_name", None),
                    "blog_slug": post.get("blog_slug", None),
                    "content_html": post.get("content_html", None),
                    "content_text": post.get("content_text", "content_text"),
                    "images": post.get("images", None),
                    "updated_at": post.get("updated_at", None),
                    "published_at": post.get("published_at", None),
                    "image": post.get("image", None),
                    "language": post.get("language", None),
                    "reference": post.get("reference", None),
                    "relationships": post.get("relationships", None),
                    "summary": post.get("summary", ""),
                    "tags": post.get("tags", None),
                    "title": post.get("title", None),
                    "url": post.get("url", None),
                    "archive_url": post.get("archive_url", None),
                },
                returning="representation",
                ignore_duplicates=False,
                on_conflict="url",
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
    )


def get_references(content_html: str):
    """Extract references from content_html,
    defined as the text after the tag "References</h2>",
    "References</h3>" or "References</h4>"""
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
        doi = is_doi(url)

        if doi:
            return {
                "key": f"ref{index + 1}",
                "doi": url,
            }
        else:
            return {
                "key": f"ref{index + 1}",
                "url": url,
            }

    references = [format_reference(url, index) for index, url in enumerate(urls)]
    return references


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


def get_abstract(content_html: str = None, maxlen: int = 450):
    """Get abstract from content_html."""
    if not content_html:
        return None
    content_html = re.sub(r"(<br>|<p>)", " ", content_html)
    content_html = re.sub(r"(h1>|h2>|h3>|h4>)", "strong>", content_html)
    sanitized = nh3.clean(
        content_html, tags={"b", "i", "em", "strong", "sub", "sup"}, attributes={}
    )
    truncated = py_.truncate(sanitized, maxlen, omission="", separator=" ")
    
    # remove incomplete last sentence
    if truncated[:-1] not in [".", "!", "?", ":"]:
        sentences = re.split(r"(?<=\w{3}[.!?])\s+", truncated)
        truncated = " ".join(sentences[:-2])
    truncated = re.sub(r"\n+", " ", truncated).strip()
    return truncated or ""


def get_relationships(content_html: str):
    """Get relationships from content_html. Extract links from
    Acknowledgments section,defined as the text after the tag
    "Acknowledgments</h2>", "Acknowledgments</h3>" or "Acknowledgments</h4>"""

    # const relationships_html = content_html.split(
    #     /(?:Acknowledgments)<\/(?:h2|h3|h4)>/,
    #     2
    # )

    # if (relationships_html.length == 1) {
    #     return []
    # }

    # // strip optional text after notes, using <hr>, <hr />, <h2, <h3, <h4 as tag
    # relationships_html[1] = relationships_html[1].split(
    #     /(?:<hr \/>|<hr>|<h2|<h3|<h4)/,
    #     2
    # )[0]

    # // split notes into sentences and classify relationship type for each sentence
    # const sentences = relationships_html[1].split(/(?<=\w{3}[.!?])\s+/)

    # const relationships = sentences
    #     .map((sentence) => {
    #     sentence = sentence.trim()
    #     const urls = getUrls(sentence).filter((url) => {
    #         const uri = new URL(url)

    #         return uri.host !== "orcid.org"
    #     })

    #     // detect type of relationship, default is generic relationship
    #     let type = "IsRelatedTo"

    #     if (sentence.search(/(originally published|cross-posted)/i) > -1) {
    #         type = "IsIdenticalTo"
    #     } else if (sentence.search(/peer-reviewed version/i) > -1) {
    #         type = "IsPreprintOf"
    #     } else if (sentence.search(/work was funded/i) > -1) {
    #         type = "HasAward"
    #     } else {
    #         // console.log(sentence)
    #     }
    #     return urls.map((url) => {
    #         return {
    #         type: type,
    #         url: url,
    #         }
    #     })
    #     })
    #     .flat()
    relationships = []

    return relationships


def get_images(soup, url: str, home_page_url: str):
    """Extract images from content_html."""

    def extract_img(image):
        """Extract url from link."""
        src = image.attrs.get("src", None)

        # src = getSrcUrl(src, url, home_page_url)
        srcset = image.attrs.get("srcset", None)

        # TODO: relative urls
        # if (isString(srcset)) {
        #     srcset = srcset
        #     .split(", ")
        #     .map((src) => getSrcUrl(src, url, home_page_url))
        #     .join(", ")
        # }
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
                "alt": alt,
            }
        )

    images = [extract_img(i) for i in soup.find_all("img")]
    return images


def get_urls(content_html: str):
    """Extract urls from html."""
    soup = BeautifulSoup(content_html, "html.parser")

    def extract_url(link):
        """Extract url from link."""
        return link.get("href")

    urls = [extract_url(i) for i in soup.find_all("a")]

    if not urls or len(urls) == 0:
        return []

    def clean_url(url):
        """Clean url."""
        url = normalize_url(url)
        if not url:
            return None
        if is_doi(url):
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
