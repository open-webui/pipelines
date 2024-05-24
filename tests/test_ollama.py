import time

def test_ollama(client, app, ollama_pipeline):
    app.state.PIPELINES["ollama_pipeline"] = {
        "module": ollama_pipeline,
        "id": ollama_pipeline.id,
        "name": ollama_pipeline.name,
    }
    response = client.get("/models")
    assert response.status_code == 200
    assert response.json() == {
        "data": [
            {
                "id": "ollama_pipeline",
                "name": "Ollama Pipeline",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "openai",
                "pipeline": True,
            }
        ]
    }
    response = client.post(
        "/chat/completions",
        json={
            "model": "ollama_pipeline",
            "stream": False,
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi!"},
            ],
        },
    )
    assert response.status_code == 200
