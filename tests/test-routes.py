import pytest  # noqa: F401
import pytest_asyncio  # noqa: F401
import pydash as py_  # noqa: F401

from rogue_scholar_api import app

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
    assert response.headers["Location"] == "https://rogue-scholar.org"


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
    assert len(result) == 60
    assert result[0]["title"] == "A blog by Ross Mounce"
    assert result[0]["slug"] == "rossmounce"


async def test_single_blog_route():
    """Test single blog route."""
    test_client = app.test_client()
    response = await test_client.get("/blogs/andrewheiss")
    assert response.status_code == 200
    result = await response.get_json()
    assert result["title"] == "Andrew Heiss's blog"
    assert result["feed_url"] == "https://www.andrewheiss.com/atom.xml"


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
    response = await test_client.get("/posts?query=retraction-watch&page=2&per_page=10")
    assert response.status_code == 200
    result = await response.get_json()
    assert result["found"] == 18
    post = py_.get(result, "hits[0].document")
    assert post["title"] == "Are more retractions due to more scrutiny?"
    assert post["doi"] == "https://doi.org/10.59350/jgggm-t5x67"


@pytest.mark.vcr
async def test_posts_with_blog_slug_route():
    """Test posts route with blog_slug."""
    test_client = app.test_client()
    response = await test_client.get("/posts?blog_slug=rossmounce")
    assert response.status_code == 200
    result = await response.get_json()
    assert result["found"] == 127
    post = py_.get(result, "hits[0].document")
    assert post["title"] is not None


@pytest.mark.vcr
async def test_posts_with_query_and_include_fields_route():
    """Test posts route with query and include fields."""
    test_client = app.test_client()
    response = await test_client.get("/posts?query=retraction-watch&include_fields=doi,title")
    assert response.status_code == 200
    result = await response.get_json()
    assert result["found"] == 18
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
    assert result["found"] == 18
    post0 = py_.get(result, "hits[0].document")
    post1 = py_.get(result, "hits[1].document")
    assert post0["published_at"] > post1["published_at"]


@pytest.mark.vcr
async def test_posts_not_indexed_route():
    """Test posts not_indexed route."""
    test_client = app.test_client()
    response = await test_client.get("/posts/not_indexed")
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
    assert len(result) == 15


@pytest.mark.vcr
async def test_posts_filter_by_tags_route():
    """Test posts route with tags filter."""
    test_client = app.test_client()
    response = await test_client.get("/posts?tags=open+access")
    assert response.status_code == 200
    result = await response.get_json()
    assert result["found"] == 615
    post = py_.get(result, "hits[0].document")
    assert (
        post["title"] == "Institutional Change toward Open Scholarship and Open Science"
    )


@pytest.mark.vcr
async def test_posts_filter_by_language_route():
    """Test posts route with language filter."""
    test_client = app.test_client()
    response = await test_client.get("/posts?language=es")
    assert response.status_code == 200
    result = await response.get_json()
    assert result["found"] == 48
    post = py_.get(result, "hits[0].document")
    assert post["title"] == "¿Qué libros científicos publicamos?"


async def test_post_route():
    """Test post route."""
    test_client = app.test_client()
    response = await test_client.get("/posts/77b2102f-fec5-425a-90a3-4a97c768bdc4")
    assert response.status_code == 200
    result = await response.get_json()
    assert result["title"] == "¿Qué libros científicos publicamos?"
    assert result["doi"] == "https://doi.org/10.59350/sfzv4-xdb68"


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
    assert result["title"] == "¿Qué libros científicos publicamos?"
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
    response = await test_client.get("/posts/10.59350/sfzv4-xdb68?format=bibtex")
    assert response.status_code == 200
    result = await response.get_data(as_text=True)
    assert (
        result
        == """@article{Fern_ndez_2023,
\tdoi = {10.59350/sfzv4-xdb68},
\turl = {https://doi.org/10.59350%2Fsfzv4-xdb68},
\tyear = 2023,
\tmonth = {oct},
\tpublisher = {Front Matter},
\tauthor = {Norbisley Fern{\\'{a}}ndez},
\ttitle = {{\\textquestiondown}Qu{\\'{e}} libros cient{\\'{\\i}}ficos publicamos?}
}"""
    )


@pytest.mark.vcr
async def test_post_as_ris():
    """Test post formatted as ris."""
    test_client = app.test_client()
    response = await test_client.get("/posts/10.59350/sfzv4-xdb68?format=ris")
    assert response.status_code == 200
    result = await response.get_data(as_text=True)
    type_ = result.splitlines()[0]
    doi = result.splitlines()[1]
    assert type_ == "TY  - GENERIC"
    assert doi == "DO  - 10.59350/sfzv4-xdb68"


@pytest.mark.vcr
async def test_post_as_csl():
    """Test post formatted as csl."""
    test_client = app.test_client()
    response = await test_client.get("/posts/10.59350/sfzv4-xdb68?format=csl")
    assert response.status_code == 200
    result = await response.get_json()
    assert result["type"] == "posted-content"
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
        == "Fernández, N. (2023). ¿Qué libros científicos publicamos? https://doi.org/10.59350/sfzv4-xdb68"
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
        == "1. Fernández N. ¿Qué libros científicos publicamos? 2023 Oct 6; Available from: http://dx.doi.org/10.59350/sfzv4-xdb68"
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
        == "1. Fernández N. ¿Qué libros científicos publicamos? 6 de octubre de 2023; Disponible en: http://dx.doi.org/10.59350/sfzv4-xdb68"
    )


@pytest.mark.vcr
async def test_post_not_found():
    """Test post not found."""
    test_client = app.test_client()
    response = await test_client.get("/posts/10.59350/sfzv4-xdb69")
    assert response.status_code == 404
    result = await response.get_json()
    assert result == {"error": "Post not found"}
