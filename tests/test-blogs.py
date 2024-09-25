"""Test blogs"""
import pytest  # noqa: F401

from api.blogs import (
    extract_single_blog,
    extract_all_blogs,
    update_single_blog,
    parse_generator,
    parse_feed_format,
    find_feed,
)


@pytest.fixture(scope="session")
def vcr_config():
    """VCR configuration."""
    return {"filter_headers": ["apikey", "key", "X-TYPESENSE-API-KEY", "authorization"]}


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_all_blogs():
    "extract all blogs"
    result = await extract_all_blogs()
    assert len(result) > 65
    blog = result[0]
    assert blog["slug"] == "rossmounce"
    assert blog["feed_url"] == "https://rossmounce.co.uk/feed/atom"


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_single_blog_atom_feed():
    "extract single blog atom feed"
    slug = "epub_fis"
    result = await extract_single_blog(slug)
    assert result["slug"] == slug
    assert result["title"] == "FIS & EPub"
    assert result["feed_url"] == "https://blog.dini.de/EPub_FIS/feed/atom/"
    assert result["home_page_url"] == "https://blog.dini.de/EPub_FIS"
    assert result["generator"] == "WordPress"
    assert result["created_at"] == 1689897600
    assert result["updated_at"] > 0
    assert (
        result["favicon"]
        == "https://blog.dini.de/EPub_FIS/wp-content/uploads/2018/03/cropped-DINI-AG-FIS-3-1-150x150.png"
    )


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_single_blog_json_feed():
    "extract single blog json feed"
    slug = "ropensci"
    result = await extract_single_blog(slug)
    assert result["slug"] == slug
    assert result["title"] == "rOpenSci - open tools for open science"
    assert result["feed_url"] == "https://ropensci.org/blog/index.json"
    assert result["home_page_url"] == "https://ropensci.org/blog"
    assert result["generator"] == "Hugo"
    assert result["created_at"] == 1693440000
    assert result["updated_at"] > 0
    assert result["favicon"] == "https://ropensci.org/apple-touch-icon.png"


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_single_blog_rss_feed():
    "extract single blog rss feed"
    slug = "andrewheiss"
    result = await extract_single_blog(slug)
    assert result["slug"] == slug
    assert result["title"] == "Andrew Heiss's blog"
    assert result["feed_url"] == "https://www.andrewheiss.com/atom.xml"
    assert result["home_page_url"] == "https://www.andrewheiss.com"
    assert result["generator"] == "Quarto"
    assert result["created_at"] == 1692662400
    assert result["updated_at"] > 0
    assert result["favicon"] is None


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_find_feed_ghost():
    "find feed in ghost homepage"
    url = "https://blog.front-matter.io/"
    result = await find_feed(url)
    assert result == "https://blog.front-matter.io/atom/"


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_find_feed_wordpress():
    "find feed in wordpress homepage"
    url = "https://ulirockenbauch.blog"
    result = await find_feed(url)
    assert result == "https://ulirockenbauch.blog/feed/"


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_find_feed_wordpress_subfolder():
    "find feed in wordpress homepage"
    url = "https://www.ch.imperial.ac.uk/rzepa/blog/"
    result = await find_feed(url)
    assert result == "https://www.ch.imperial.ac.uk/rzepa/blog/?feed=rss2"


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_find_feed_hugo():
    "find feed in hugo homepage"
    url = "https://sven-lieber.org/en/"
    result = await find_feed(url)
    assert result == "https://sven-lieber.org/en/index.xml"


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_find_feed_quarto():
    "find feed in quarto homepage"
    url = "https://www.andrewheiss.com/"
    result = await find_feed(url)
    assert result is None


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_find_feed_blogger():
    "find feed in blogger homepage"
    url = "https://iphylo.blogspot.com/"
    result = await find_feed(url)
    assert result == "https://iphylo.blogspot.com/feeds/posts/default"


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_find_feed_jekyll():
    "find feed in jekyll homepage"
    url = "https://eve.gd/"
    result = await find_feed(url)
    assert result == "https://eve.gd/feed/feed.atom"


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_find_feed_substack():
    "find feed in substack homepage"
    url = "https://cwagen.substack.com/"
    result = await find_feed(url)
    assert result == "https://cwagen.substack.com/feed"


def test_parse_generator_hugo():
    """Parse generator hugo"""
    generator = {"href": "https://gohugo.io", "name": "Hugo 0.110.0"}
    result = parse_generator(generator)
    assert result == "Hugo 0.110.0"


def test_parse_generator_wordpress():
    """Parse generator wordpress"""
    generator = {
        "version": "6.2.3",
        "href": "https://wordpress.org/",
        "name": "WordPress",
    }
    result = parse_generator(generator)
    assert result == "WordPress 6.2.3"


def test_parse_generator_wordpress_alternate():
    """Parse generator wordpress alternate format"""
    generator = {"name": "https://wordpress.org/?v=6.4.2"}
    result = parse_generator(generator)
    assert result == "WordPress 6.4.2"


def test_parse_generator_wordpress_com():
    """Parse generator wordpress.com"""
    generator = {"href": "http://wordpress.com/", "name": "WordPress.com"}
    result = parse_generator(generator)
    assert result == "WordPress.com"


def test_parse_generator_ghost():
    """Parse generator ghost"""
    generator = {"version": "5.52", "href": "https://ghost.org", "name": "Ghost"}
    result = parse_generator(generator)
    assert result == "Ghost 5.52"


def test_parse_generator_jekyll():
    """Parse generator jekyll"""
    generator = {"version": "3.9.3", "href": "https://jekyllrb.com/", "name": "Jekyll"}
    result = parse_generator(generator)
    assert result == "Jekyll 3.9.3"


def test_parse_generator_substack():
    """Parse generator substack"""
    generator = {"name": "Substack"}
    result = parse_generator(generator)
    assert result == "Substack"


def test_parse_generator_medium():
    """Parse generator medium"""
    generator = {"name": "Medium"}
    result = parse_generator(generator)
    assert result == "Medium"


def test_parse_generator_blogger():
    """Parse generator blogger"""
    generator = {"version": "7.00", "href": "http://www.blogger.com", "name": "Blogger"}
    result = parse_generator(generator)
    assert result == "Blogger 7.00"


def test_parse_generator_quarto():
    """Parse generator quarto"""
    generator = {"name": "quarto-1.2.475"}
    result = parse_generator(generator)
    assert result == "Quarto 1.2.475"


def test_parse_generator_site_server():
    """Parse generator site-server"""
    generator = {
        "name": "Site-Server v6.0.0-2103de5ef4113dede0a855ecc535e943ec13f6ba-1 (http://www.squarespace.com)"
    }
    result = parse_generator(generator)
    assert result == "Squarespace 6.0.0"


def test_parse_feed_format_atom():
    """Parse feed format atom"""
    feed_format = {
        "links": [
            {
                "href": "https://blog.dini.de/EPub_FIS/feed/atom/",
                "rel": "self",
                "type": "application/atom+xml",
            },
            {
                "href": "https://blog.dini.de/EPub_FIS/feed/atom/",
                "rel": "alternate",
                "type": "text/html",
            },
        ]
    }
    result = parse_feed_format(feed_format)
    assert result == "application/atom+xml"


def test_parse_feed_format_rss():
    """Parse feed format rss"""
    feed_format = {
        "links": [
            {
                "rel": "alternate",
                "type": "text/html",
                "href": "https://tarleb.com/index.html",
            },
            {
                "href": "https://tarleb.com/index.xml",
                "rel": "self",
                "type": "application/rss+xml",
            },
        ]
    }
    result = parse_feed_format(feed_format)
    assert result == "application/rss+xml"


def test_parse_feed_format_json_feed():
    """Parse feed format json feed"""
    feed_format = {
        "links": [
            {
                "rel": "alternate",
                "type": "text/html",
                "href": "https://tarleb.com/index.html",
            },
            {
                "href": "https://tarleb.com/index.xml",
                "rel": "self",
                "type": "application/rss+xml",
            },
        ]
    }
    result = parse_feed_format(feed_format)
    assert result == "application/rss+xml"


@pytest.mark.vcr
def test_update_single_blog():
    """Upsert single blog"""
    blog = {
        "slug": "epub_fis",
        "feed_url": "https://blog.dini.de/EPub_FIS/feed/atom/",
        "created_at": "2023-07-21",
        "updated_at": 1695639719,
        "current_feed_url": None,
        "home_page_url": "https://blog.dini.de/EPub_FIS",
        "archive_prefix": None,
        "feed_format": "application/atom+xml",
        "title": "FIS & EPub",
        "generator": "WordPress 6.3.2",
        "description": "Gemeinsamer Blog der DINI AG Forschungsinformationssystem und Elektronisches Publizieren",
        "favicon": "https://blog.dini.de/EPub_FIS/wp-content/uploads/2018/03/cropped-DINI-AG-FIS-3-1-150x150.png",
        "language": "de",
        "license": "https://creativecommons.org/licenses/by/4.0/legalcode",
        "category": "socialSciences",
        "status": "active",
        "user_id": "a9e3541e-1e00-4bf3-8a4d-fc9b1c505651",
        "authors": None,
        "mastodon": None,
        "use_api": True,
        "relative_url": None,
        "filter": None,
    }
    result = update_single_blog(blog)
    assert result["title"] == "FIS & EPub"
    assert result["slug"] == "epub_fis"
