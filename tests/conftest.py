import importlib.util
from pathlib import Path
from fastapi.testclient import TestClient

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent


def import_module(module_path):
    spec = importlib.util.spec_from_file_location("module", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def ollama_pipeline():
    module = import_module(BASE_DIR / "pipelines" / "ollama_pipeline.py")
    return module.Pipeline()


@pytest.fixture(scope="session")
def app():
    from open_webui.pipelines.main import app

    return app

@pytest.fixture(scope="session")
def client(app):
    return TestClient(app)
