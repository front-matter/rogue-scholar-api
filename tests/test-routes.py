import pytest  # noqa: F401
import pytest_asyncio  # noqa: F401
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
    assert result["found"] > 65
    post = py_.get(result, "hits[0].document")
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
async def test_blogs_with_include_fields_route():
    """Test blogs route with include fields."""
    test_client = app.test_client()
    response = await test_client.get("/blogs?include_fields=slug,title")
    assert response.status_code == 200
    result = await response.get_json()
    assert result["found"] > 65
    post = py_.get(result, "hits[0].document")
    assert "slug" in post.keys()
    assert "description" not in post.keys()


@pytest.mark.vcr
async def test_blogs_sort_route():
    """Test blogs route with sort."""
    test_client = app.test_client()
    response = await test_client.get("/blogs?sort=title&order=asc")
    assert response.status_code == 200
    result = await response.get_json()
    assert result["found"] > 65
    post0 = py_.get(result, "hits[0].document")
    post1 = py_.get(result, "hits[1].document")
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
    assert len(result) == 0


@pytest.mark.vcr
async def test_posts_unregistered_route():
    """Test posts unregistered route."""
    test_client = app.test_client()
    response = await test_client.get("/posts/unregistered")
    assert response.status_code == 200
    result = await response.get_json()
    assert len(result) == 0


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
    assert len(result) > 0
    post = result[0]
    assert post["title"] is not None


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
        == """@article{Fern_ndez_2023,
 author = {Fernández, Norbisley},
 doi = {10.59350/sfzv4-xdb68},
 month = {October},
 publisher = {Front Matter},
 title = {¿Qué libros científicos publicamos en Ediciones Universidad de Camagüey?},
 url = {http://dx.doi.org/10.59350/sfzv4-xdb68},
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
    doi = result.splitlines()[1]
    assert type_ == "TY  - GENERIC"
    assert doi == "DO  - 10.59350/sfzv4-xdb68"


@pytest.mark.vcr
async def test_post_as_markdown():
    """Test post formatted as markdown."""
    test_client = app.test_client()
    response = await test_client.get("/posts/10.59350/sfzv4-xdb68.md")
    assert response.status_code == 200
    result = await response.get_data(as_text=True)
    assert result is not None


@pytest.mark.vcr
async def test_post_as_xml():
    """Test post formatted as xml."""
    test_client = app.test_client()
    response = await test_client.get("/posts/10.59350/sfzv4-xdb68.xml")
    assert response.status_code == 200
    result = await response.get_data(as_text=True)
    assert result is not None


@pytest.mark.vcr
async def test_post_as_epub():
    """Test post formatted as epub."""
    test_client = app.test_client()
    response = await test_client.get("/posts/10.59350/sfzv4-xdb68.epub")
    assert response.status_code == 200
    result = await response.get_data()
    assert result is not None


@pytest.mark.vcr
async def test_post_as_pdf():
    """Test post formatted as pdf."""
    test_client = app.test_client()
    response = await test_client.get("/posts/10.59350/sfzv4-xdb68.pdf")
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
    assert result["type"] == "article-journal"
    assert result["title"] == "¿Qué libros científicos publicamos en Ediciones Universidad de Camagüey?"
    assert result["container-title"] == "Edición y comunicación de la Ciencia"
    assert result["DOI"] == "10.59350/sfzv4-xdb68"


@pytest.mark.vcr
async def test_post_as_citation():
    """Test post as formatted citation."""
    test_client = app.test_client()
    response = await test_client.get("/posts/10.59350/sfzv4-xdb68?format=citation")
    assert response.status_code == 200
    result = await response.get_data(as_text=True)
    assert (
        result
        == "Fernández, N. (2023). ¿Qué libros científicos publicamos en Ediciones Universidad de Camagüey? https://doi.org/10.59350/sfzv4-xdb68"
    )


@pytest.mark.vcr
async def test_post_as_citation_with_style():
    """Test post as formatted citation with vancouver style."""
    test_client = app.test_client()
    response = await test_client.get(
        "/posts/10.59350/sfzv4-xdb68?format=citation&style=vancouver"
    )
    assert response.status_code == 200
    result = await response.get_data(as_text=True)
    assert (
        result
        == "1.Fernández N. ¿Qué libros científicos publicamos en Ediciones Universidad de Camagüey? 2023 Oct 6; Available from: http://dx.doi.org/10.59350/sfzv4-xdb68"
    )


@pytest.mark.vcr
async def test_post_as_citation_with_locale():
    """Test post as formatted citation with locale."""
    test_client = app.test_client()
    response = await test_client.get(
        "/posts/10.59350/sfzv4-xdb68?format=citation&style=vancouver&locale=es"
    )
    assert response.status_code == 200
    result = await response.get_data(as_text=True)
    assert (
        result
        == "1.Fernández N. ¿Qué libros científicos publicamos en Ediciones Universidad de Camagüey? 6 de octubre de 2023; Disponible en: http://dx.doi.org/10.59350/sfzv4-xdb68"
    )


@pytest.mark.vcr
async def test_post_not_found():
    """Test post not found."""
    test_client = app.test_client()
    response = await test_client.get("/posts/10.59350/sfzv4-xdb69")
    assert response.status_code == 404
    result = await response.get_json()
    assert result == {"error": "Post not found"}
