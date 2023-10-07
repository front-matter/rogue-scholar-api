from rogue_scholar_api import app
import pytest  # noqa: F401
import pytest_asyncio  # noqa: F401
import pydash as py_  # noqa: F401

pytestmark = pytest.mark.asyncio


async def test_index_route():
    test_client = app.test_client()
    response = await test_client.get("/")
    assert response.status_code == 200
    result = await response.data
    print(result)
    assert result == b"This is the Rogue Scholar API."


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
