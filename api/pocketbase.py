"""Pocketbase client configuration"""
from os import environ
from dotenv import load_dotenv
from pocketbase import PocketBase

load_dotenv()

pocketbase_client = PocketBase(environ["QUART_POCKETBASE_URL"])
pocketbase_user = environ["QUART_POCKETBASE_USER"]
pocketbase_password = environ["QUART_POCKETBASE_PASSWORD"]
admin_data = pocketbase_client.admins.auth_with_password(pocketbase_user, pocketbase_password)
