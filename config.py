import os

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
    TYPESENSE_API_KEY = os.environ.get("TYPESENSE_API_KEY")
    TYPESENSE_HOST = os.environ.get("TYPESENSE_HOST")
