"""Typesense client configuration"""
from os import environ
from dotenv import load_dotenv
from typesense import Client as TypesenseClient

load_dotenv()

typesense_client = TypesenseClient(
    {
        "api_key": environ["QUART_TYPESENSE_API_KEY"],
        "nodes": [
            {
                "host": environ["QUART_TYPESENSE_HOST"],
                "port": "443",
                "protocol": "https",
            }
        ],
    }
)
