from rogue_scholar_api import app
import pytest  # noqa: F401
import pytest_asyncio  # noqa: F401

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
