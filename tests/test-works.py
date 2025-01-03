"""Test works"""

import pytest  # noqa: F401
import pydash as py_  # noqa: F401

from api.works import get_single_work


@pytest.mark.asyncio
async def test_get_single_work_blog_post():
    """get single work not found"""
    string = "10.53731/ybhah-9jy85"
    work = await get_single_work(string)
    assert work["id"] == "https://doi.org/10.53731/ybhah-9jy85"
    assert work["type"] == "Article"
    assert (
        work["url"]
        == "https://blog.front-matter.io/posts/the-rise-of-the-science-newsletter"
    )
    assert work.get("language", None) == None


@pytest.mark.asyncio
async def test_get_single_work_journal_article():
    """get single work journal article"""
    string = "10.1038/d41586-023-02554-0"
    work = await get_single_work(string)
    assert work["id"] == "https://doi.org/10.1038/d41586-023-02554-0"
    assert work["type"] == "JournalArticle"
    assert work["url"] == "https://www.nature.com/articles/d41586-023-02554-0"


@pytest.mark.asyncio
async def test_get_single_work_software():
    """get single work software"""
    string = "10.5281/zenodo.8340374"
    work = await get_single_work(string)
    assert work["id"] == "https://doi.org/10.5281/zenodo.8340374"
    assert work["type"] == "Software"
    assert work["url"] == "https://zenodo.org/doi/10.5281/zenodo.8340374"


@pytest.mark.asyncio
async def test_get_single_work_dataset():
    """get single work dataset"""
    string = "10.5281/zenodo.7834392"
    work = await get_single_work(string)
    assert work["id"] == "https://doi.org/10.5281/zenodo.7834392"
    assert work["type"] == "Dataset"
    assert work["url"] == "https://zenodo.org/record/7834392"
