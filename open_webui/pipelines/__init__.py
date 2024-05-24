import os

####################################
# Load .env file
####################################

try:
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv("./.env"))
except ImportError:
    print("dotenv not installed, skipping...")

from .main import app  # noqa
