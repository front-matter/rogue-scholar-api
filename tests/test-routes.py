import pytest  # noqa: F401
import pydash as py_  # noqa: F401
from os import environ

from api import app

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="session")
def vcr_config():
    """VCR configuration."""
    return {"filter_headers": ["apikey", "X-TYPESENSE-API-KEY", "authorization"]}


async def test_index_route():
    """Test index route."""
    test_client = app.test_client()
    response = await test_client.get("/")
    assert response.status_code == 301
    assert response.headers["Location"] == "/posts"


async def test_heartbeat_route():
    """Test heartbeat route."""
    test_client = app.test_client()
    response = await test_client.get("/heartbeat")
    assert response.status_code == 200
    assert await response.get_data(as_text=True) == "OK"


async def test_works_redirect_route():
    """Test works redirect route."""
    test_client = app.test_client()
    response = await test_client.get("/works/")
    assert response.status_code == 301
    assert response.headers["Location"] == "/works"


@pytest.mark.vcr
async def test_works_route():
    """Test works route."""
    test_client = app.test_client()
    response = await test_client.get("/works")
    assert response.status_code == 200
    result = await response.get_json()
    assert result["total-results"] > 40
    work = py_.get(result, "items.0")
    assert work["titles"] is not None


@pytest.mark.vcr
async def test_work_route():
    """Test work route."""
    test_client = app.test_client()
    response = await test_client.get("/works/c2182771-c786-4c51-b3db-4f5c599948f3")
    assert response.status_code == 200
    result = await response.get_json()
    assert result["id"] == "https://doi.org/10.1038/d41586-023-02554-0"
    assert result["type"] == "JournalArticle"
    assert result["titles"] == [
        {
            "title": "Thousands of scientists are cutting back on Twitter, seeding angst and uncertainty"
        }
    ]
    assert result["date"] == {"published": "2023-08-16"}


async def test_blogs_redirect_route():
    """Test blogs redirect route."""
    test_client = app.test_client()
    response = await test_client.get("/blogs/")
    assert response.status_code == 301
    assert response.headers["Location"] == "/blogs"


@pytest.mark.vcr
async def test_blogs_route():
    """Test blogs route."""
    test_client = app.test_client()
    response = await test_client.get("/blogs")
    assert response.status_code == 200
    result = await response.get_json()
    assert result["total-results"] > 65
    post = py_.get(result, "items[0]")
    assert post["title"] is not None


@pytest.mark.vcr
async def test_blogs_with_query_and_pagination_route():
    """Test blogs route with query and pagination."""
    test_client = app.test_client()
    response = await test_client.get("/blogs?query=wordpress&page=2&per_page=10")
    assert response.status_code == 200
    result = await response.get_json()
    assert result["found"] > 25
    post = py_.get(result, "hits[0].document")
    assert post["title"] is not None


@pytest.mark.vcr
async def test_blogs_sort_route():
    """Test blogs route with sort."""
    test_client = app.test_client()
    response = await test_client.get("/blogs?sort=title&order=asc")
    assert response.status_code == 200
    result = await response.get_json()
    assert result["total-results"] > 65
    post0 = py_.get(result, "items[0]")
    post1 = py_.get(result, "items[1]")
    assert post0["title"] < post1["title"]


@pytest.mark.vcr
async def test_blogs_post_route():
    """Test blogs post route."""
    test_client = app.test_client()
    key = environ["QUART_SUPABASE_SERVICE_ROLE_KEY"]
    headers = {"Authorization": f"Bearer {key}"}
    response = await test_client.post("/blogs", headers=headers)
    assert response.status_code == 200
    result = await response.get_json()
    assert len(result) > 60
    assert result[0]["title"] == "A blog by Ross Mounce"
    assert result[0]["slug"] == "rossmounce"


@pytest.mark.vcr
async def test_single_blog_route():
    """Test single blog route."""
    test_client = app.test_client()
    response = await test_client.get("/blogs/andrewheiss")
    assert response.status_code == 200
    result = await response.get_json()
    assert result["title"] == "Andrew Heiss's blog"
    assert result["feed_url"] == "https://www.andrewheiss.com/atom.xml"


@pytest.mark.vcr
async def test_single_blog_post_route():
    """Test single blog post route."""
    test_client = app.test_client()
    key = environ["QUART_SUPABASE_SERVICE_ROLE_KEY"]
    headers = {"Authorization": f"Bearer {key}"}
    response = await test_client.post("/blogs/andrewheiss", headers=headers)
    assert response.status_code == 200
    result = await response.get_json()
    assert result["title"] == "Andrew Heiss's blog"
    assert result["feed_url"] == "https://www.andrewheiss.com/atom.xml"


@pytest.mark.vcr
async def test_single_blog_with_posts_rss_route():
    """Test single blog with posts rss route."""
    test_client = app.test_client()
    key = environ["QUART_SUPABASE_SERVICE_ROLE_KEY"]
    headers = {"Authorization": f"Bearer {key}"}
    response = await test_client.post("/blogs/andrewheiss/posts", headers=headers)
    assert response.status_code == 200
    result = await response.get_json()
    assert len(result) == 0


@pytest.mark.vcr
async def test_single_blog_with_posts_json_feed_route():
    """Test single blog with posts json feed route."""
    test_client = app.test_client()
    key = environ["QUART_SUPABASE_SERVICE_ROLE_KEY"]
    headers = {"Authorization": f"Bearer {key}"}
    response = await test_client.post("/blogs/ropensci/posts?page=1", headers=headers)
    assert response.status_code == 200
    result = await response.get_json()
    assert len(result) == 0


async def test_posts_redirect_route():
    """Test posts redirect route."""
    test_client = app.test_client()
    response = await test_client.get("/posts/")
    assert response.status_code == 301
    assert response.headers["Location"] == "/posts"


async def test_posts_route():
    """Test posts route."""
    test_client = app.test_client()
    response = await test_client.get("/posts")
    assert response.status_code == 200
    result = await response.get_json()
    assert result["found"] > 9070
    post = py_.get(result, "hits[0].document")
    assert post["title"] is not None


@pytest.mark.vcr
async def test_posts_with_query_and_pagination_route():
    """Test posts route with query and pagination."""
    test_client = app.test_client()
    response = await test_client.get("/posts?query=retraction-watch&page=1&per_page=10")
    assert response.status_code == 200
    result = await response.get_json()
    assert result["found"] > 5
    post = py_.get(result, "hits[0].document")
    assert post["title"] is not None


@pytest.mark.vcr
async def test_posts_with_query_by_author_url():
    """Test posts route with query by author url."""
    test_client = app.test_client()
    response = await test_client.get(
        "/posts?query=0000-0003-1419-2405&query_by=authors.url"
    )
    assert response.status_code == 200
    result = await response.get_json()
    assert result["found"] > 500
    post = py_.get(result, "hits[0].document")
    assert post["title"] is not None


@pytest.mark.vcr
async def test_posts_with_blog_slug_route():
    """Test posts route with blog_slug."""
    test_client = app.test_client()
    response = await test_client.get("/posts?blog_slug=rossmounce")
    assert response.status_code == 200
    result = await response.get_json()
    assert result["found"] > 125
    post = py_.get(result, "hits[0].document")
    assert post["title"] is not None


@pytest.mark.vcr
async def test_posts_with_query_and_include_fields_route():
    """Test posts route with query and include fields."""
    test_client = app.test_client()
    response = await test_client.get(
        "/posts?query=retraction-watch&include_fields=doi,title"
    )
    assert response.status_code == 200
    result = await response.get_json()
    assert result["found"] > 5
    post = py_.get(result, "hits[0].document")
    assert "doi" in post.keys()
    assert "summary" not in post.keys()


@pytest.mark.vcr
async def test_posts_with_query_and_sort_route():
    """Test posts route with query and sort."""
    test_client = app.test_client()
    response = await test_client.get("/posts?query=retraction-watch&sort=published_at")
    assert response.status_code == 200
    result = await response.get_json()
    assert result["found"] > 5
    post0 = py_.get(result, "hits[0].document")
    post1 = py_.get(result, "hits[1].document")
    assert post0["published_at"] > post1["published_at"]


@pytest.mark.vcr
async def test_posts_updated_route():
    """Test posts updated route."""
    test_client = app.test_client()
    response = await test_client.get("/posts/updated")
    assert response.status_code == 200
    result = await response.get_json()
    assert len(result) > 0


@pytest.mark.vcr
async def test_posts_unregistered_route():
    """Test posts unregistered route."""
    test_client = app.test_client()
    response = await test_client.get("/posts/unregistered")
    assert response.status_code == 200
    result = await response.get_json()
    assert len(result) > 0


@pytest.mark.vcr
async def test_posts_filter_by_published_since_route():
    """Test posts route with published_since and published_until filters."""
    test_client = app.test_client()
    response = await test_client.get(
        "/posts?published_since=2023-10-06&published_until=2023-10-12"
    )
    assert response.status_code == 200
    result = await response.get_json()
    assert result["found"] > 20
    post = py_.get(result, "hits[0].document")
    assert post["title"] is not None


@pytest.mark.vcr
async def test_posts_filter_by_tags_route():
    """Test posts route with tags filter."""
    test_client = app.test_client()
    response = await test_client.get("/posts?tags=open+access")
    assert response.status_code == 200
    result = await response.get_json()
    assert result["found"] > 750
    post = py_.get(result, "hits[0].document")
    assert post["title"] is not None and "Open Access" in post["tags"]


@pytest.mark.vcr
async def test_posts_filter_by_language_route():
    """Test posts route with language filter."""
    test_client = app.test_client()
    response = await test_client.get("/posts?language=es")
    assert response.status_code == 200
    result = await response.get_json()
    assert result["found"] > 90
    post = py_.get(result, "hits[0].document")
    assert post["language"] == "es"


async def test_posts_post_route():
    """Test posts post route."""
    test_client = app.test_client()
    key = environ["QUART_SUPABASE_SERVICE_ROLE_KEY"]
    headers = {"Authorization": f"Bearer {key}"}
    response = await test_client.post("/posts", headers=headers)
    assert response.status_code == 200
    result = await response.get_json()
    # post = result[0]
    # assert post["title"] is not None


@pytest.mark.vcr
async def test_post_route():
    """Test post route."""
    test_client = app.test_client()
    response = await test_client.get("/posts/77b2102f-fec5-425a-90a3-4a97c768bdc4")
    assert response.status_code == 200
    result = await response.get_json()
    assert (
        result["title"]
        == "¿Qué libros científicos publicamos en Ediciones Universidad de Camagüey?"
    )
    assert result["doi"] == "https://doi.org/10.59350/sfzv4-xdb68"
    assert result["language"] == "es"


async def test_post_invalid_uuid_route():
    """Test post route with invalid uuid."""
    test_client = app.test_client()
    response = await test_client.get("/posts/77b2102f-fec5-425a-90a3-4a97c768")
    assert response.status_code == 400
    result = await response.get_json()
    assert result["error"] == "An error occured."


async def test_post_not_found_route():
    """Test post route with uuid not found."""
    test_client = app.test_client()
    response = await test_client.get("/posts/77b2102f-fec5-425a-90a3-4a97c7689999")
    assert response.status_code == 404
    result = await response.get_json()
    assert result["error"] == "Post not found"


async def test_post_route_by_doi():
    """Test post route by doi."""
    test_client = app.test_client()
    response = await test_client.get("/posts/10.59350/sfzv4-xdb68")
    assert response.status_code == 200
    result = await response.get_json()
    assert (
        result["title"]
        == "¿Qué libros científicos publicamos en Ediciones Universidad de Camagüey?"
    )
    assert result["doi"] == "https://doi.org/10.59350/sfzv4-xdb68"
    assert result["id"] == "77b2102f-fec5-425a-90a3-4a97c768bdc4"


async def test_post_route_by_doi_not_found():
    """Test post route by doi not found."""
    test_client = app.test_client()
    response = await test_client.get("/posts/10.59350/sfzv4-xdbxx")
    assert response.status_code == 404
    result = await response.get_json()
    assert result["error"] == "Post not found"


@pytest.mark.vcr
async def test_post_as_bibtex():
    """Test post formatted as bibtex."""
    test_client = app.test_client()
    response = await test_client.get("/posts/10.59350/sfzv4-xdb68.bib")
    assert response.status_code == 200
    result = await response.get_data(as_text=True)
    assert (
        result
        == """@article{10.59350/sfzv4-xdb68,
    abstract = {{.wp-image-523 attachment-id=“523” permalink=“https://norbisley.wordpress.com/2023/10/06/que-libros-cientificos-publicamos/rrm1esyb-3/” orig-file=“https://norbisley.files.wordpress.com/2023/10/rrm1esyb-3.png” orig-size=“1008,301” comments-opened=“1” image-meta=“{"aperture":"0","credit":"","camera":"","caption":"","created_timestamp":"0","copyright":"","focal_length":"0","iso":"0","shutter_speed":"0","title":"","orientation":"0"}”},
    author = {Fernández, Norbisley},
    copyright = {https://creativecommons.org/licenses/by/4.0/legalcode},
    doi = {10.59350/sfzv4-xdb68},
    journal = {Edición y comunicación de la Ciencia},
    language = {es},
    month = oct,
    title = {¿Qué libros científicos publicamos en Ediciones Universidad de Camagüey?},
    url = {https://norbisley.wordpress.com/2023/10/06/que-libros-cientificos-publicamos},
    urldate = {2023-10-06},
    year = {2023}
}"""
    )


@pytest.mark.vcr
async def test_post_as_ris():
    """Test post formatted as ris."""
    test_client = app.test_client()
    response = await test_client.get("/posts/10.59350/sfzv4-xdb68.ris")
    assert response.status_code == 200
    result = await response.get_data(as_text=True)
    type_ = result.splitlines()[0]
    title = result.splitlines()[1]
    assert type_ == "TY  - JOUR"
    assert (
        title
        == "T1  - ¿Qué libros científicos publicamos en Ediciones Universidad de Camagüey?"
    )


@pytest.mark.vcr
async def test_post_as_markdown():
    """Test post formatted as markdown."""
    test_client = app.test_client()
    response = await test_client.get("/posts/10.53731/ybhah-9jy85.md")
    assert response.status_code == 200
    result = await response.get_data(as_text=True)
    assert result is not None


@pytest.mark.vcr
async def test_post_as_xml():
    """Test post formatted as xml."""
    test_client = app.test_client()
    response = await test_client.get("/posts/10.53731/ybhah-9jy85.xml")
    assert response.status_code == 200
    result = await response.get_data(as_text=True)
    assert result is not None


@pytest.mark.vcr
async def test_post_as_epub():
    """Test post formatted as epub."""
    test_client = app.test_client()
    response = await test_client.get("/posts/10.53731/ybhah-9jy85.epub")
    assert response.status_code == 200
    result = await response.get_data()
    assert result is not None


@pytest.mark.vcr
async def test_post_as_pdf():
    """Test post formatted as pdf."""
    test_client = app.test_client()
    response = await test_client.get("/posts/10.53731/ybhah-9jy85.pdf")
    assert response.status_code == 200
    result = await response.get_data()
    assert result is not None


@pytest.mark.vcr
async def test_post_as_csl():
    """Test post formatted as csl."""
    test_client = app.test_client()
    response = await test_client.get("/posts/10.59350/sfzv4-xdb68?format=csl")
    assert response.status_code == 200
    result = await response.get_json()
    assert result["type"] == "article"
    assert (
        result["title"]
        == "¿Qué libros científicos publicamos en Ediciones Universidad de Camagüey?"
    )
    assert result["container-title"] == "Edición y comunicación de la Ciencia"
    assert result["DOI"] == "10.59350/sfzv4-xdb68"


@pytest.mark.vcr
async def test_post_uuid_as_csl():
    """Test post uuid formatted as csl."""
    test_client = app.test_client()
    response = await test_client.get(
        "/posts/77b2102f-fec5-425a-90a3-4a97c768bdc4?format=csl"
    )
    assert response.status_code == 200
    result = await response.get_json()
    assert result["type"] == "article"
    assert (
        result["title"]
        == "¿Qué libros científicos publicamos en Ediciones Universidad de Camagüey?"
    )
    assert result["container-title"] == "Edición y comunicación de la Ciencia"
    assert result["DOI"] == "10.59350/sfzv4-xdb68"


@pytest.mark.vcr
async def test_post_as_citation():
    """Test post as formatted citation. Default style is apa."""
    test_client = app.test_client()
    response = await test_client.get("/posts/10.53731/dnfg0-hge29?format=citation")
    assert response.status_code == 200
    result = await response.get_data(as_text=True)
    assert (
        result
        == "Fenner, M. (2024). An update on Rogue Scholar in the fediverse. <i>Front Matter</i>. https://doi.org/10.53731/dnfg0-hge29"
    )


@pytest.mark.vcr
async def test_post_as_citation_with_style():
    """Test post as formatted citation with vancouver style."""
    test_client = app.test_client()
    response = await test_client.get(
        "/posts/10.53731/dnfg0-hge29?format=citation&style=vancouver"
    )
    assert response.status_code == 200
    result = await response.get_data(as_text=True)
    assert (
        result
        == "1. Fenner M. An update on Rogue Scholar in the fediverse. Front Matter [Internet]. 2024Jan29;. Available from: https://blog.front-matter.io/posts/an-update-on-the-rogue-scholar-fediverse"
    )


# TODO: issue with citeproc library
# @pytest.mark.vcr
# async def test_post_as_citation_with_locale():
#     """Test post as formatted citation with locale."""
#     test_client = app.test_client()
#     response = await test_client.get(
#         "/posts/10.53731/dnfg0-hge29?format=citation&style=vancouver&locale=de"
#     )
#     assert response.status_code == 200
#     result = await response.get_data(as_text=True)
#     assert (
#         result
#         == "Fernández, N. (2023). ¿Qué libros científicos publicamos en Ediciones Universidad de Camagüey?. <i>Edición y comunicación de la ciencia</i>. https://doi.org/10.59350/sfzv4-xdb68"
#     )


@pytest.mark.vcr
async def test_post_not_found():
    """Test post not found."""
    test_client = app.test_client()
    response = await test_client.get("/posts/10.59350/sfzv4-xdb69")
    assert response.status_code == 404
    result = await response.get_json()
    assert result == {"error": "Post not found"}


async def test_post_route_references():
    """Test post route references."""
    test_client = app.test_client()
    response = await test_client.get("/posts/10.53731/r79z0kh-97aq74v-ag5hb/references")
    assert response.status_code == 200
    result = await response.get_json()
    assert result["total-results"] == 16
    assert len(result["items"]) == 16
    result = result["items"][6]
    assert result["key"] == "ref7"
    assert result["id"] == "https://doi.org/10.1016/j.aeolia.2015.08.001"
    assert result["title"] == "Racetrack Playa: Rocks moved by wind alone"
    assert result["publicationYear"] == "2015"
