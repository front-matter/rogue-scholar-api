import requests


def get_doi_metadata_from_ra(doi: str, headers) -> str:
    """use DOI content negotiation to get metadata in various formats"""
    response = requests.get(doi, headers=headers)
    if response.status_code >= 400:
        return "Metadata not found"
    return response.text.strip()


# def format_metadata(meta: dict, to: str = "bibtex"):
#     """use commonmeta-py library to format metadata into various formats"""
#     print(meta)
#     subject = Metadata(meta)

#     if to == "bibtex":
#         return write_bibtex(subject)
#     elif to == "ris":
#         return write_ris(subject)
#     elif to == "csl":
#         return write_csl(subject)
#     elif to == "citation":
#         return write_citation(subject)
