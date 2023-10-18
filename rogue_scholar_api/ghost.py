"""Ghost client configuration"""
from os import environ
from dotenv import load_dotenv
from ghost import GhostContent

load_dotenv()


def ghost_api(url: str, slug: str):
    """Return Ghost API."""
    return GhostContent(
        url,
        contentAPIKey=environ[f"QUART_{slug.upper()}_GHOST_API_KEY"],
        api_version="v5.0",
    )
