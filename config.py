import os
from pathlib import Path

####################################
# Load .env file
####################################

try:
    from dotenv import load_dotenv, find_dotenv

    load_dotenv(find_dotenv("./.env"))
except ImportError:
    print("dotenv not installed, skipping...")

API_KEY = os.getenv("PIPELINES_API_KEY", "0p3n-w3bu!")
PIPELINES_DIR = os.getenv("PIPELINES_DIR", "./pipelines")


####################################
# Database
####################################
DATA_DIR = Path(os.getenv("DATA_DIR", "data")).resolve()
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DATA_DIR}/webui.db")
