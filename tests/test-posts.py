"""Test posts"""
import pytest  # noqa: F401
from datetime import datetime
from rogue_scholar_api.posts import (
    extract_all_posts_by_blog,
    get_urls,
    get_references
    # get_title,
    # get_abstract,
)


@pytest.fixture(scope="session")
def vcr_config():
    """VCR configuration."""
    return {"filter_headers": ["apikey", "key", "X-TYPESENSE-API-KEY", "authorization"]}


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_all_posts_by_blog_wordpress():
    """Extract all posts by blog wordpress"""
    slug = "epub_fis"
    result = await extract_all_posts_by_blog(slug, page=1, update_all=True)
    assert len(result) == 50
    post = result[0]
    assert post["title"] == "Aktualisierte OpenAIRE Richtlinie für FIS-Manager"
    assert post["authors"][0] == {"name": "Gastautor(en)"}
    assert post["tags"] == [
        "Elektronisches Publizieren",
        "Forschungsinformationssysteme",
        "Projekt",
        "OpenAIRE",
    ]


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_all_posts_by_blog_wordpresscom():
    """Extract all posts by blog wordpresscom"""
    slug = "wisspub"
    result = await extract_all_posts_by_blog(slug, page=1, update_all=True)
    assert len(result) == 50
    post = result[0]
    assert (
        post["title"]
        == "DOIs für Wissenschaftsblogs? – Ein Interview mit Martin Fenner zu Rogue Scholar"
    )
    assert post["authors"][0] == {
        "name": "Heinz Pampel",
        "url": "https://orcid.org/0000-0003-3334-2771",
    }
    assert post["tags"] == [
        "Langzeitarchivierung",
        "Open Science",
        "Publikationsverhalten",
        "Web 2.0",
        "Wissenschaftskommunikation",
    ]


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_all_posts_by_blog_ghost():
    """Extract all posts by blog ghost"""
    slug = "front_matter"
    result = await extract_all_posts_by_blog(slug, page=1, update_all=True)
    assert len(result) == 50
    post = result[0]
    assert post["title"] == "Generating Overlay blog posts"
    assert post["authors"][0] == {
        "name": "Martin Fenner",
        "url": "https://orcid.org/0000-0003-1419-2405",
    }
    assert len(post["images"]) == 1
    assert post["images"][0] == {
        "alt": "",
        "height": "190",
        "sizes": "(min-width: 720px) 720px",
        "src": "https://blog.front-matter.io/content/images/2023/10/mermaid-figure-1.png",
        "srcset": "https://blog.front-matter.io/content/images/size/w600/2023/10/mermaid-figure-1.png "
        "600w, "
        "https://blog.front-matter.io/content/images/size/w1000/2023/10/mermaid-figure-1.png "
        "1000w, "
        "https://blog.front-matter.io/content/images/size/w1600/2023/10/mermaid-figure-1.png "
        "1600w, "
        "https://blog.front-matter.io/content/images/size/w2400/2023/10/mermaid-figure-1.png "
        "2400w",
        "width": "2000",
    }
    assert (
        post["image"]
        == "https://images.unsplash.com/flagged/photo-1552425083-0117136f7d67?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3wxMTc3M3wwfDF8c2VhcmNofDIxfHxjYW5vcHl8ZW58MHx8fHwxNjk3MDQwMDk1fDA&ixlib=rb-4.0.3&q=80&w=2000"
    )
    assert len(post["reference"]) == 3
    assert (
        post["reference"][0]
        == {'doi': 'https://doi.org/10.53731/ar11b-5ea39', 'key': 'ref1'}
    )
    assert post["tags"] == ["Feature"]


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_all_posts_by_blog_ghost_updated():
    """Extract all posts by blog ghost updated only"""
    slug = "front_matter"
    result = await extract_all_posts_by_blog(slug, page=1, update_all=False)
    assert len(result) == 0


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_all_posts_by_blog_substack():
    """Extract all posts by blog substack"""
    slug = "cwagen"
    result = await extract_all_posts_by_blog(slug, page=1, update_all=True)
    assert len(result) == 50
    post = result[0]
    assert post["title"] == "Networking, For Skeptics"
    assert post["authors"][0] == {
        "name": "Corin Wagen",
        "url": "https://orcid.org/0000-0003-3315-3524",
    }
    assert post["tags"] == []


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_all_posts_by_blog_json_feed():
    """Extract all posts by blog json feed"""
    slug = "ropensci"
    result = await extract_all_posts_by_blog(slug, page=1, update_all=True)
    assert len(result) == 50
    post = result[0]
    assert post["title"] == "How to Translate a Hugo Blog Post with Babeldown"
    assert post["authors"][0] == {
        "name": "Maëlle Salmon",
        "url": "https://orcid.org/0000-0002-2815-0399",
    }
    assert (
        post["url"]
        == "https://ropensci.org/blog/2023/09/26/how-to-translate-a-hugo-blog-post-with-babeldown"
    )
    assert len(post["reference"]) == 0
    assert post["tags"] == ["Tech Notes", "Multilingual"]


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_all_posts_by_blog_json_feed_updated():
    """Extract all posts by blog json feed only updated"""
    slug = "ropensci"
    result = await extract_all_posts_by_blog(slug, page=1, update_all=False)
    assert len(result) == 50
    post = result[1]
    assert post["title"] == "rOpenSci News Digest, September 2023"
    assert (
        datetime.fromtimestamp(post["updated_at"]).isoformat() == "2023-09-22T09:59:27"
    )


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_all_posts_by_blog_json_feed_with_pagination():
    """Extract all posts by blog json feed with pagination"""
    slug = "ropensci"
    result = await extract_all_posts_by_blog(slug, page=2, update_all=True)
    assert len(result) == 50
    post = result[0]
    assert post["title"] == "How to Save ggplot2 Plots in a targets Workflow?"
    assert post["url"] == "https://ropensci.org/blog/2022/12/06/save-ggplot2-targets"
    assert post["tags"] == ["Targets", "Ggplot2", "Workflow", "Tech Notes", "Community"]


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_all_posts_by_blog_blogger():
    """Extract all posts by blogger blog"""
    slug = "iphylo"
    result = await extract_all_posts_by_blog(slug, page=3, update_all=True)
    assert len(result) == 50
    post = result[0]
    assert post["title"] == "TDWG 2017: thoughts on day 1"
    assert post["authors"][0] == {
        "name": "Roderic Page",
        "url": "https://orcid.org/0000-0002-7101-9767",
    }
    assert (
        post["url"]
        == "https://iphylo.blogspot.com/2017/10/tdwg-2017-thoughts-on-day-1.html"
    )
    assert len(post["reference"]) == 0
    assert post["tags"] == ["BHL", "GBIF", "Knowledge Graph", "Linked Data", "TDWG"]


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_all_posts_by_blog_atom():
    """Extract all posts by blog atom"""
    slug = "eve"
    result = await extract_all_posts_by_blog(slug, page=3, update_all=True)
    assert len(result) == 50
    post = result[0]
    assert (
        post["title"]
        == "The Publisher's Association's impact assessment on OA is pretty much as you'd expect"
    )
    assert post["authors"][0] == {
        "name": "Martin Paul Eve",
        "url": "https://orcid.org/0000-0002-5589-8511",
    }
    assert (
        post["url"]
        == "https://eve.gd/2021/02/17/the-publishers-associations-impact-assessment-on-oa"
    )
    assert post["tags"] == []


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_extract_all_posts_by_blog_rss():
    """Extract all posts by blog rss"""
    slug = "tarleb"
    result = await extract_all_posts_by_blog(slug, page=1, update_all=True)
    assert len(result) == 18
    post = result[0]
    assert post["title"] == "Typst Musings"
    assert post["authors"][0] == {"name": "Albert Krewinkel"}
    assert post["tags"] == ["PDF"]


def test_get_urls():
    """Get urls"""
    html = "Bla bla <a href='https://iphylo.blogspot.com/feeds/posts/default?start-index=1&max-results=50'>."
    result = get_urls(html)
    assert result == [
        "https://iphylo.blogspot.com/feeds/posts/default?start-index=1&max-results=50"
    ]


def test_get_references():
    """Extract references"""
    html ="""Bla. <h2>References</h2><p>Fenner, M. (2023). <em>Rogue Scholar has an API</em>. 
    <a href="https://doi.org/10.53731/ar11b-5ea39">https://doi.org/10.53731/ar11b-5ea39</a></p>
    <p>Crossref, Hendricks, G., Center for Scientific Integrity, &amp; Lammey, R. (2023). 
    <em>Crossref acquires Retraction Watch data and opens it for the scientific community</em>. 
    <a href="https://doi.org/10.13003/c23rw1d9">https://doi.org/10.13003/c23rw1d9</a></p>"""
    
    result = get_references(html)
    assert len(result) == 2
    assert result[0] == {'doi': 'https://doi.org/10.53731/ar11b-5ea39', 'key': 'ref1'}


# def test_get_title():
#     """Sanitize title."""
#     title = "Bla <img src='#'/><i>bla</i>"
#     result = get_title(title)
#     assert result == "Bla <i>bla</i>"


# def test_get_abstract():
#     """Sanitize and truncate abstract."""
#     abstract = """
#     There’s something special about language. It is ‘our own’, it is ‘us’, in a profound way, and quite surprisingly, more so than art. I was deeply struck by this when I first saw reactions to large generative language models that created realistic, human-ish prose. Notably, those mature enough to reach a non-professional audience – ChatGPT based on GPT-3 and later GPT-4 – came quite some time after models that could create fairly acceptable visual ‘art’.1 The appearance of synthetic language-like products (SLLPs), as I like to call the output of such generative models, came well after the appearance of synthetic simulacra of visual art,2 yet elicited much less fervent responses."""
#     result = get_abstract(abstract)
#     print(result)
#     assert result.endswith("human-ish prose.")
