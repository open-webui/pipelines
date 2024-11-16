import os


####################################
# Load .env file
####################################

try:
    from dotenv import load_dotenv, find_dotenv

    load_dotenv(find_dotenv("./.env"))
except ImportError:
    print("dotenv not installed, skipping...")

API_KEY = os.getenv("PIPELINES_API_KEY", "0p3n-w3bu!")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

PIPELINES_DIR = os.getenv("PIPELINES_DIR", "./pipelines")
RESET_PIPELINES_DIR = os.getenv("RESET_PIPELINES_DIR", "false").lower() == "true"
PIPELINES_REQUIREMENTS_PATH = os.getenv("PIPELINES_REQUIREMENTS_PATH")
PIPELINES_URLS = os.getenv("PIPELINES_URLS")

SUPPRESS_PIP_OUTPUT = os.getenv("SUPPRESS_PIP_OUTPUT", "true").lower() == "true"
