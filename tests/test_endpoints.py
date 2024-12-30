import sys
import pytest
from pathlib import Path
import json
from unittest.mock import patch, mock_open
from fastapi.testclient import TestClient

# need to add the parent directory to the path to import the main module
sys.path.append(str(Path(__file__).resolve().parent.parent))
from main import app

# using the app object from the main module
client = TestClient(app)

def test_get_status():
    response = client.get("/v1")
    assert response.status_code == 200
    assert response.json() == {"status": True}

# TODO: check other endpoints from the client -- both mocked and URL-based
