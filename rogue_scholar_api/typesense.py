from os import environ
from dotenv import load_dotenv
from typesense import Client as TypesenseClient

load_dotenv()
typesense_host: str = environ.get("TYPESENSE_HOST")
typesense_api_key: str = environ.get("TYPESENSE_API_KEY")

typesense_client = TypesenseClient(
    {
        "api_key": typesense_api_key,
        "nodes": [
            {
                "host": typesense_host,
                "port": "443",
                "protocol": "https",
            }
        ],
    }
)
