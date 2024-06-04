"""
title: Cohere Manifold Pipeline
author: justinh-rahb
date: 2024-05-28
version: 1.0
license: MIT
description: A pipeline for generating text using the Anthropic API.
requirements: requests
environment_variables: COHERE_API_KEY
"""

import os
import json
from schemas import OpenAIChatMessage
from typing import List, Union, Generator, Iterator
from pydantic import BaseModel
import requests


class Pipeline:
    class Valves(BaseModel):
        COHERE_API_BASE_URL: str = "https://api.cohere.com/v1"
        COHERE_API_KEY: str = ""

    def __init__(self):
        self.type = "manifold"

        # Optionally, you can set the id and name of the pipeline.
        # Best practice is to not specify the id so that it can be automatically inferred from the filename, so that users can install multiple versions of the same pipeline.
        # The identifier must be unique across all pipelines.
        # The identifier must be an alphanumeric string that can include underscores or hyphens. It cannot contain spaces, special characters, slashes, or backslashes.

        self.id = "cohere"

        self.name = "cohere/"

        self.valves = self.Valves(
            **{"COHERE_API_KEY": os.getenv("COHERE_API_KEY", "your-api-key-here")}
        )

        self.pipelines = self.get_cohere_models()

    async def on_startup(self):
        print(f"on_startup:{__name__}")
        pass

    async def on_shutdown(self):
        print(f"on_shutdown:{__name__}")
        pass

    async def on_valves_updated(self):
        # This function is called when the valves are updated.

        self.pipelines = self.get_cohere_models()

        pass

    def get_cohere_models(self):
        if self.valves.COHERE_API_KEY:
            try:
                headers = {}
                headers["Authorization"] = f"Bearer {self.valves.COHERE_API_KEY}"
                headers["Content-Type"] = "application/json"

                r = requests.get(
                    f"{self.valves.COHERE_API_BASE_URL}/models", headers=headers
                )

                models = r.json()
                return [
                    {
                        "id": model["name"],
                        "name": model["name"] if "name" in model else model["name"],
                    }
                    for model in models["models"]
                ]
            except Exception as e:

                print(f"Error: {e}")
                return [
                    {
                        "id": self.id,
                        "name": "Could not fetch models from Cohere, please update the API Key in the valves.",
                    },
                ]
        else:
            return []

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        try:
            if body.get("stream", False):
                return self.stream_response(user_message, model_id, messages, body)
            else:
                return self.get_completion(user_message, model_id, messages, body)
        except Exception as e:
            return f"Error: {e}"

    def stream_response(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Generator:

        headers = {}
        headers["Authorization"] = f"Bearer {self.valves.COHERE_API_KEY}"
        headers["Content-Type"] = "application/json"

        r = requests.post(
            url=f"{self.valves.COHERE_API_BASE_URL}/chat",
            json={
                "model": model_id,
                "chat_history": [
                    {
                        "role": "USER" if message["role"] == "user" else "CHATBOT",
                        "message": message["content"],
                    }
                    for message in messages[:-1]
                ],
                "message": user_message,
                "stream": True,
            },
            headers=headers,
            stream=True,
        )

        r.raise_for_status()

        for line in r.iter_lines():
            if line:
                try:
                    line = json.loads(line)
                    if line["event_type"] == "text-generation":
                        yield line["text"]
                except:
                    pass

    def get_completion(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> str:
        headers = {}
        headers["Authorization"] = f"Bearer {self.valves.COHERE_API_KEY}"
        headers["Content-Type"] = "application/json"

        r = requests.post(
            url=f"{self.valves.COHERE_API_BASE_URL}/chat",
            json={
                "model": model_id,
                "chat_history": [
                    {
                        "role": "USER" if message["role"] == "user" else "CHATBOT",
                        "message": message["content"],
                    }
                    for message in messages[:-1]
                ],
                "message": user_message,
            },
            headers=headers,
        )

        r.raise_for_status()
        data = r.json()

        return data["text"] if "text" in data else "No response from Cohere."
