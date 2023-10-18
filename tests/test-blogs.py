"""Test blogs"""
import pytest  # noqa: F401

from rogue_scholar_api.blogs import (
    extract_single_blog,
    parse_generator,
    parse_feed_format,
)


def test_extract_single_blog():
    "extract single blog"
    slug = "epub_fis"
    result = extract_single_blog(slug)
    assert result["slug"] == slug
    assert result["title"] == "FIS & EPub"
    assert result["feed_url"] == "https://blog.dini.de/EPub_FIS/feed/atom/"
    assert result["home_page_url"] == "https://blog.dini.de/EPub_FIS"
    assert result["generator"] == "WordPress 6.3.2"
    assert (
        result["favicon"]
        == "https://blog.dini.de/EPub_FIS/wp-content/uploads/2018/03/cropped-DINI-AG-FIS-3-1-150x150.png"
    )


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
