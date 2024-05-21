import os

####################################
# Load .env file
####################################

try:
    from dotenv import load_dotenv, find_dotenv

    load_dotenv(find_dotenv("./.env"))
except ImportError:
    print("dotenv not installed, skipping...")


MODEL_ID = os.environ.get("MODEL_ID", "plugin-id")
MODEL_NAME = os.environ.get("MODEL_NAME", "Plugin Model")
