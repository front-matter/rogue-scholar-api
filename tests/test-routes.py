from rogue_scholar_api import app
import pytest  # noqa: F401
import pytest_asyncio  # noqa: F401
import pydash as py_  # noqa: F401

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="session")
def vcr_config():
    return {"filter_headers": ["apikey", "X-TYPESENSE-API-KEY", "authorization"]}


async def test_index_route():
    test_client = app.test_client()
    response = await test_client.get("/")
    assert response.status_code == 200
    result = await response.get_data(as_text=True)
    assert result == "This is the Rogue Scholar API."


@pytest.mark.vcr
async def test_blogs_route():
    test_client = app.test_client()
    response = await test_client.get("/blogs")
    assert response.status_code == 200
    result = await response.get_json()
    assert len(result) == 60
    assert result[0]["title"] == "A blog by Ross Mounce"
    assert result[0]["slug"] == "rossmounce"


async def test_single_blog_route():
    test_client = app.test_client()
    response = await test_client.get("/blogs/andrewheiss")
    assert response.status_code == 200
    result = await response.get_json()
    assert result["title"] == "Andrew Heiss's blog"
    assert result["feed_url"] == "https://www.andrewheiss.com/atom.xml"


async def test_posts_route():
    test_client = app.test_client()
    response = await test_client.get("/posts")
    assert response.status_code == 200
    result = await response.get_json()
    posts = result["hits"]
    assert len(posts) == 10
    post = py_.get(posts, "[0].document")
    assert post["title"] == "¿Qué libros científicos publicamos?"
    assert post["doi"] == "https://doi.org/10.59350/sfzv4-xdb68"


@pytest.mark.vcr
async def test_posts_with_query_and_pagination_route():
    test_client = app.test_client()
    response = await test_client.get("/posts?query=retraction-watch&page=2")
    assert response.status_code == 200
    result = await response.get_json()
    posts = result["hits"]
    assert len(posts) == 8
    post = py_.get(posts, "[0].document")
    assert post["title"] == "Are more retractions due to more scrutiny?"
    assert post["doi"] == "https://doi.org/10.59350/jgggm-t5x67"


@pytest.mark.vcr
async def test_posts_not_indexed_route():
    test_client = app.test_client()
    response = await test_client.get("/posts/not_indexed")
    assert response.status_code == 200
    result = await response.get_json()
    assert len(result) == 0
    # post = result[0]
    # assert post["title"] == "¿Qué libros científicos publicamos?"
    # assert post["doi"] == "https://doi.org/10.59350/sfzv4-xdb68"


@pytest.mark.vcr
async def test_posts_unregistered_route():
    test_client = app.test_client()
    response = await test_client.get("/posts/unregistered")
    assert response.status_code == 200
    result = await response.get_json()
    assert len(result) == 15
    post = result[0]
    assert (
        post["title"]
        == "Transmediale-Festival untersucht den „Full Take“ unserer Daten"
    )
    assert post["blog_slug"] == "irights"


async def test_post_route():
    test_client = app.test_client()
    response = await test_client.get("/posts/77b2102f-fec5-425a-90a3-4a97c768bdc4")
    assert response.status_code == 200
    result = await response.get_json()
    assert result["title"] == "¿Qué libros científicos publicamos?"
    assert result["doi"] == "https://doi.org/10.59350/sfzv4-xdb68"


async def test_post_route_by_doi():
    test_client = app.test_client()
    response = await test_client.get("/posts/10.59350/sfzv4-xdb68")
    assert response.status_code == 200
    result = await response.get_json()
    assert result["title"] == "¿Qué libros científicos publicamos?"
    assert result["doi"] == "https://doi.org/10.59350/sfzv4-xdb68"


@pytest.mark.vcr
async def test_post_as_bibtex():
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
async def test_post_as_citation():
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
