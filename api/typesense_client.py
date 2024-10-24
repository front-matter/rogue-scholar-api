"""Typesense client configuration"""
from os import environ
from dotenv import load_dotenv
from typesense import Client as TypesenseClient

load_dotenv()

typesense_client = TypesenseClient(
    {
        "api_key": environ.get("QUART_TYPESENSE_ANON_KEY", "abc"),
        "nodes": [
            {
                "host": environ.get("QUART_TYPESENSE_HOST", None),
                "port": "443",
                "protocol": "https",
            }
        ],
    }
)
