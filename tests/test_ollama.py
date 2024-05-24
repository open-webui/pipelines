import time


def test_ollama(client, ollama_pipeline, pipeline):
    response = client.get("/models")
    assert response.status_code == 200
    response_json = response.json()
    data = response_json["data"]
    assert len(data) == 2
    assert data[0] == {
        "id": "ollama_pipeline",
        "name": "Ollama Pipeline",
        "object": "model",
        "created": int(time.time()),
        "owned_by": "openai",
        "pipeline": True,
    }
    assert data[1] == {
        "id": "pipeline",
        "name": "Pipeline",
        "object": "model",
        "created": int(time.time()),
        "owned_by": "openai",
        "pipeline": True,
    }
    for message_content in ["Hello", "Hi", "Hey"]:
        response = client.post(
            "/chat/completions",
            json={
                "model": "pipeline",
                "stream": False,
                "messages": [
                    {"role": "user", "content": message_content},
                ],
            },
        )
        assert response.status_code == 200
        response_json = response.json()
        assert response_json["model"] == "pipeline"
        assert response_json["id"].startswith("pipeline-") and len(
            response_json["id"]
        ) == len("pipeline-") + 36
        choices = response_json["choices"]
        assert len(choices) == 1 and choices[0]["finish_reason"] == "stop"
        assert choices[0]["message"]["content"] == f"pipeline response to: {message_content}"
    # skip ollama pipeline for now because it takes too long
