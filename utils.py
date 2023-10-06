import requests


def get_doi_metadata(doi: str, headers) -> str:
    """use DOI content negotiation to get metadata in various formats"""
    response = requests.get(doi, headers=headers)
    if response.status_code >= 400:
        return "Metadata not found"
    return response.text.strip()
