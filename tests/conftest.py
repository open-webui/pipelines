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


@pytest.fixture(scope="session")
def ollama_pipeline(app):
    module = import_module(BASE_DIR / "pipelines" / "ollama_pipeline.py")
    ollama_pipeline = module.Pipeline()
    app.state.PIPELINES[ollama_pipeline.id] = {
        "module": ollama_pipeline,
        "id": ollama_pipeline.id,
        "name": ollama_pipeline.name,
    }
    return ollama_pipeline


@pytest.fixture(scope="session")
def pipeline(app):
    module = import_module(BASE_DIR / "pipelines" / "pipeline.py")
    module.__name__ = "pipeline"
    pipeline = module.Pipeline()
    app.state.PIPELINES["pipeline"] = {
        "module": pipeline,
        "id": "pipeline",
        "name": "Pipeline",
    }
    return pipeline


@pytest.fixture(scope="session")
def app():
    from open_webui.pipelines.main import app

    return app

@pytest.fixture(scope="session")
def client(app):
    return TestClient(app)
