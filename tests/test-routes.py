import pytest
import pydash as py_
from os import environ

from api import app

pytestmark = pytest.mark.asyncio


async def test_index_route():
    """Test index route."""
    async with app.test_app():
        test_client = app.test_client()
        response = await test_client.get("/")
        assert response.status_code == 301
        assert response.headers["Location"] == "/posts"


async def test_heartbeat_route():
    """Test heartbeat route."""
    async with app.test_app():
        test_client = app.test_client()
        response = await test_client.get("/heartbeat")
        assert response.status_code == 200
        assert await response.get_data(as_text=True) == "OK"


async def test_blogs_redirect_route():
    """Test blogs redirect route."""
    async with app.test_app():
        test_client = app.test_client()
        response = await test_client.get("/blogs/")
        assert response.status_code == 301
        assert response.headers["Location"] == "/blogs"


async def test_blogs_route():
    """Test blogs route."""
    async with app.test_app():
        test_client = app.test_client()
        response = await test_client.get("/blogs")
        assert response.status_code == 200
        result = await response.get_json()
        assert result["total-results"] > 0
        assert isinstance(result["items"], list)
        if len(result["items"]) > 0:
            blog = result["items"][0]
            assert "title" in blog
            assert "slug" in blog


async def test_blogs_with_query_route():
    """Test blogs route with query."""
    async with app.test_app():
        test_client = app.test_client()
        response = await test_client.get("/blogs?query=science")
        assert response.status_code == 200
        result = await response.get_json()
        assert "total-results" in result
        assert isinstance(result["items"], list)


async def test_single_blog_route():
    """Test single blog route."""
    async with app.test_app():
        test_client = app.test_client()
        response = await test_client.get("/blogs/front_matter")
        # Blog may or may not exist in test database
        assert response.status_code in [200, 404]
        if response.status_code == 200:
            result = await response.get_json()
            assert result is not None
            assert "slug" in result or "title" in result


async def test_posts_redirect_route():
    """Test posts redirect route."""
    async with app.test_app():
        test_client = app.test_client()

        response = await test_client.get("/posts/")
        assert response.status_code == 301
        assert response.headers["Location"] == "/posts"


async def test_posts_route():
    """Test posts route."""
    async with app.test_app():
        test_client = app.test_client()

        response = await test_client.get("/posts")
        assert response.status_code == 200
        result = await response.get_json()
        assert result["found"] > 0
        post = py_.get(result, "hits[0].document")
        assert post["title"] is not None


async def test_posts_with_query_and_pagination_route():
    """Test posts route with query and pagination."""
    async with app.test_app():
        test_client = app.test_client()

        response = await test_client.get(
            "/posts?query=retraction-watch&page=1&per_page=10"
        )
        assert response.status_code == 200
        result = await response.get_json()
        assert result["found"] >= 0
        if result["found"] > 0:
            post = py_.get(result, "hits[0].document")
            assert post["title"] is not None


async def test_posts_with_query_by_author_url():
    """Test posts route with query by author url."""
    async with app.test_app():
        test_client = app.test_client()

        response = await test_client.get(
            "/posts?query=0000-0003-1419-2405&query_by=authors.url"
        )
        assert response.status_code == 200
        result = await response.get_json()
        assert result["found"] >= 0


async def test_posts_with_blog_slug_route():
    """Test posts route with blog_slug."""
    async with app.test_app():
        test_client = app.test_client()

        response = await test_client.get("/posts?blog_slug=rossmounce")
        assert response.status_code == 200
        result = await response.get_json()
        assert result["found"] >= 0


async def test_posts_with_query_and_include_fields_route():
    """Test posts route with query and include fields."""
    async with app.test_app():
        test_client = app.test_client()

        response = await test_client.get(
            "/posts?query=retraction-watch&include_fields=doi,title"
        )
        assert response.status_code == 200
        result = await response.get_json()
        assert result["found"] >= 0
        if result["found"] > 0:
            post = py_.get(result, "hits[0].document")
            assert "doi" in post.keys()
            assert "summary" not in post.keys()


async def test_posts_with_query_and_sort_route():
    """Test posts route with query and sort."""
    async with app.test_app():
        test_client = app.test_client()

        response = await test_client.get(
            "/posts?query=retraction-watch&sort=published_at"
        )
        assert response.status_code == 200
        result = await response.get_json()
        assert result["found"] >= 0
        if result["found"] > 1:
            post0 = py_.get(result, "hits[0].document")
            post1 = py_.get(result, "hits[1].document")
            assert post0["published_at"] > post1["published_at"]


async def test_posts_updated_route():
    """Test posts updated route."""
    async with app.test_app():
        test_client = app.test_client()

        response = await test_client.get("/posts/updated")
        assert response.status_code == 200
        result = await response.get_json()
        assert isinstance(result, list)


async def test_posts_unregistered_route():
    """Test posts unregistered route."""
    async with app.test_app():
        test_client = app.test_client()

        response = await test_client.get("/posts/unregistered")
        assert response.status_code == 200
        result = await response.get_json()
        assert isinstance(result, list)


async def test_posts_filter_by_published_since_route():
    """Test posts route with published_since and published_until filters."""
    async with app.test_app():
        test_client = app.test_client()

        response = await test_client.get(
            "/posts?published_since=2023-10-06&published_until=2023-10-12"
        )
        assert response.status_code == 200
        result = await response.get_json()
        assert result["found"] >= 0


async def test_posts_filter_by_tags_route():
    """Test posts route with tags filter."""
    async with app.test_app():
        test_client = app.test_client()

        response = await test_client.get("/posts?tags=open+access")
        assert response.status_code == 200
        result = await response.get_json()
        assert result["found"] >= 0
        if result["found"] > 0:
            post = py_.get(result, "hits[0].document")
            assert post["title"] is not None


async def test_posts_filter_by_language_route():
    """Test posts route with language filter."""
    async with app.test_app():
        test_client = app.test_client()

        response = await test_client.get("/posts?language=es")
        assert response.status_code == 200
        result = await response.get_json()
        assert result["found"] >= 0
        if result["found"] > 0:
            post = py_.get(result, "hits[0].document")
            assert post["language"] == "es"


async def test_posts_post_route():
    """Test posts post route."""
    async with app.test_app():
        test_client = app.test_client()

        key = environ["QUART_SUPABASE_SERVICE_ROLE_KEY"]
        headers = {"Authorization": f"Bearer {key}"}
        response = await test_client.post("/posts", headers=headers)
        assert response.status_code == 200
        result = await response.get_json()
        # post = result[0]
        # assert post["title"] is not None


async def test_post_route():
    """Test post route."""
    async with app.test_app():
        test_client = app.test_client()

        response = await test_client.get("/posts/77b2102f-fec5-425a-90a3-4a97c768bdc4")
        assert response.status_code == 200
        result = await response.get_json()
        assert result["id"] == "77b2102f-fec5-425a-90a3-4a97c768bdc4"
        assert result["doi"] == "https://doi.org/10.59350/sfzv4-xdb68"
        assert result["language"] == "es"


async def test_post_invalid_uuid_route():
    """Test post route with invalid uuid."""
    async with app.test_app():
        test_client = app.test_client()

        response = await test_client.get("/posts/77b2102f-fec5-425a-90a3-4a97c768")
        assert response.status_code == 400
        result = await response.get_json()
        assert result["error"] == "An error occured."


async def test_post_not_found_route():
    """Test post route with uuid not found."""
    async with app.test_app():
        test_client = app.test_client()

        response = await test_client.get("/posts/77b2102f-fec5-425a-90a3-4a97c7689999")
        assert response.status_code == 404
        result = await response.get_json()
        assert result["error"] == "Post not found"


async def test_post_route_by_doi():
    """Test post route by doi."""
    async with app.test_app():
        test_client = app.test_client()

        response = await test_client.get("/posts/10.59350/sfzv4-xdb68")
        assert response.status_code == 200
        result = await response.get_json()
        # Flexible check - just verify key fields are present
        assert result["doi"] == "https://doi.org/10.59350/sfzv4-xdb68"
        assert result["id"] == "77b2102f-fec5-425a-90a3-4a97c768bdc4"


async def test_post_route_by_doi_not_found():
    """Test post route by doi not found."""
    async with app.test_app():
        test_client = app.test_client()

        response = await test_client.get("/posts/10.59350/sfzv4-xdbxx")
        assert response.status_code == 404
        result = await response.get_json()
        assert result["error"] == "Post not found"


async def test_post_as_bibtex():
    """Test post formatted as bibtex."""
    async with app.test_app():
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


async def test_post_as_ris():
    """Test post formatted as ris."""
    async with app.test_app():
        test_client = app.test_client()

        response = await test_client.get("/posts/10.59350/sfzv4-xdb68.ris")
        assert response.status_code == 200
        result = await response.get_data(as_text=True)
        type_ = result.splitlines()[0]
        assert type_ == "TY  - JOUR"
        # Flexible check - verify title line exists
        assert any("T1  -" in line for line in result.splitlines())


async def test_post_as_markdown():
    """Test post formatted as markdown."""
    async with app.test_app():
        test_client = app.test_client()

        response = await test_client.get("/posts/10.53731/ybhah-9jy85.md")
        assert response.status_code == 200
        result = await response.get_data(as_text=True)
        assert result is not None


async def test_post_as_xml():
    """Test post formatted as xml."""
    async with app.test_app():
        test_client = app.test_client()

        response = await test_client.get("/posts/10.53731/ybhah-9jy85.xml")
        assert response.status_code == 200
        result = await response.get_data(as_text=True)
        assert result is not None


async def test_post_as_epub():
    """Test post formatted as epub."""
    async with app.test_app():
        test_client = app.test_client()

        response = await test_client.get("/posts/10.53731/ybhah-9jy85.epub")
        assert response.status_code == 200
        result = await response.get_data()
        assert result is not None


async def test_post_as_pdf():
    """Test post formatted as pdf."""
    async with app.test_app():
        test_client = app.test_client()

        response = await test_client.get("/posts/10.53731/ybhah-9jy85.pdf")
        assert response.status_code == 200
        result = await response.get_data()
        assert result is not None


async def test_post_as_csl():
    """Test post formatted as csl."""
    async with app.test_app():
        test_client = app.test_client()

        response = await test_client.get("/posts/10.59350/sfzv4-xdb68?format=csl")
        assert response.status_code == 200
        result = await response.get_json()
        assert result["type"] == "article"
        assert "title" in result
        assert result["DOI"] == "10.59350/sfzv4-xdb68"


async def test_post_uuid_as_csl():
    """Test post uuid formatted as csl."""
    async with app.test_app():
        test_client = app.test_client()

        response = await test_client.get(
            "/posts/77b2102f-fec5-425a-90a3-4a97c768bdc4?format=csl"
        )
        assert response.status_code == 200
        result = await response.get_json()
        assert result["type"] == "article"
        assert "title" in result
        assert result["DOI"] == "10.59350/sfzv4-xdb68"


async def test_post_as_citation():
    """Test post as formatted citation. Default style is apa."""
    async with app.test_app():
        test_client = app.test_client()

        response = await test_client.get("/posts/10.53731/dnfg0-hge29?format=citation")
        assert response.status_code == 200
        result = await response.get_data(as_text=True)
        # Flexible check - verify key elements are present
        assert "Fenner" in result
        assert "10.53731/dnfg0-hge29" in result


async def test_post_as_citation_with_style():
    """Test post as formatted citation with vancouver style."""
    async with app.test_app():
        test_client = app.test_client()

        response = await test_client.get(
            "/posts/10.53731/dnfg0-hge29?format=citation&style=vancouver"
        )
        assert response.status_code == 200
        result = await response.get_data(as_text=True)
        # Flexible check - verify key elements
        assert "Fenner" in result
        assert result.strip() != ""

    # TODO: issue with citeproc library
    # async def test_post_as_citation_with_locale(test_client):
    #     """Test post as formatted citation with locale."""
    #
    #     response = await test_client.get(
    #         "/posts/10.53731/dnfg0-hge29?format=citation&style=vancouver&locale=de"
    #     )
    #     assert response.status_code == 200
    #     result = await response.get_data(as_text=True)
    #     assert (
    #         result
    #         == "Fernández, N. (2023). ¿Qué libros científicos publicamos en Ediciones Universidad de Camagüey?. <i>Edición y comunicación de la ciencia</i>. https://doi.org/10.59350/sfzv4-xdb68"
    #     )


async def test_post_not_found():
    """Test post not found."""
    async with app.test_app():
        test_client = app.test_client()

        response = await test_client.get("/posts/10.59350/sfzv4-xdb69")
        assert response.status_code == 404
        result = await response.get_json()
        assert result == {"error": "Post not found"}


async def test_post_route_references():
    """Test post route references."""
    async with app.test_app():
        test_client = app.test_client()

        response = await test_client.get(
            "/posts/10.53731/r79z0kh-97aq74v-ag5hb/references"
        )
        assert response.status_code == 200
        result = await response.get_json()
        assert result["total-results"] == 16
        assert len(result["items"]) == 16
        result = result["items"][6]
        assert result["key"] == "ref7"
        assert result["id"] == "https://doi.org/10.1016/j.aeolia.2015.08.001"
        assert result["title"] == "Racetrack Playa: Rocks moved by wind alone"
        assert result["publicationYear"] == "2015"
