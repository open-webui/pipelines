"""
title: DeepSeek Manifold Pipeline
author: Mohammed El-Beltagy
date: 2025-01-20
version: 1.4
license: MIT
description: A pipeline for generating text using the DeepSeeks API.
requirements: requests, sseclient-py
environment_variables: DEEPSEEK_API_KEY
"""


import os
import requests
import json
from typing import List, Union, Generator, Iterator
from pydantic import BaseModel
import sseclient

from utils.pipelines.main import pop_system_message


class Pipeline:
    class Valves(BaseModel):
        DEEPSEEK_API_KEY: str = ""

    def __init__(self):
        self.type = "manifold"
        self.id = "deepseek"
        self.name = "deepseek/"

        self.valves = self.Valves(
            **{"DEEPSEEK_API_KEY": os.getenv("DEEPSEEK_API_KEY", "your-api-key-here")}
        )
        self.url = 'https://api.deepseek.com/chat/completions'
        self.update_headers()

    def update_headers(self):
        self.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.valves.DEEPSEEK_API_KEY}'
        }

    def get_deepseek_models(self):
        return [
            {"id": "deepseek-chat", "name": "DeepSeek Chat"},
            {"id": "deepseek-reasoner", "name": "DeepSeek R1"},
        ]

    async def on_startup(self):
        print(f"on_startup:{__name__}")
        pass

    async def on_shutdown(self):
        print(f"on_shutdown:{__name__}")
        pass

    async def on_valves_updated(self):
        self.update_headers()

    def pipelines(self) -> List[dict]:
        return self.get_deepseek_models()

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        try:
            # Remove unnecessary keys
            for key in ['user', 'chat_id', 'title']:
                body.pop(key, None)

            system_message, messages = pop_system_message(messages)

            # Process messages for DeepSeek format
            processed_messages = []
            for message in messages:
                if isinstance(message.get("content"), list):
                    # DeepSeek currently doesn't support multi-modal inputs
                    # Combine all text content
                    text_content = " ".join(
                        item["text"] for item in message["content"] 
                        if item["type"] == "text"
                    )
                    processed_messages.append({
                        "role": message["role"],
                        "content": text_content
                    })
                else:
                    processed_messages.append({
                        "role": message["role"],
                        "content": message.get("content", "")
                    })

            # Add system message if present
            if system_message:
                processed_messages.insert(0, {
                    "role": "system",
                    "content": str(system_message)
                })

            # Prepare the payload for DeepSeek API
            payload = {
                "model": model_id,
                "messages": processed_messages,
                "max_tokens": body.get("max_tokens", 4096),
                "temperature": body.get("temperature", 0.8),
                "top_p": body.get("top_p", 0.9),
                "stream": body.get("stream", False)
            }

            # Add optional parameters if present
            if "stop" in body:
                payload["stop"] = body["stop"]

            if body.get("stream", False):
                return self.stream_response(payload)
            else:
                return self.get_completion(payload)
        except Exception as e:
            return f"Error: {e}"

    def stream_response(self, payload: dict) -> Generator:
        response = requests.post(self.url, headers=self.headers, json=payload, stream=True)

        if response.status_code == 200:
            client = sseclient.SSEClient(response)
            for event in client.events():
                try:
                    data = json.loads(event.data)
                    if "choices" in data and len(data["choices"]) > 0:
                        delta = data["choices"][0].get("delta", {})
                        if "content" in delta:
                            yield delta["content"]
                        if data["choices"][0].get("finish_reason") is not None:
                            break
                except json.JSONDecodeError:
                    print(f"Failed to parse JSON: {event.data}")
                except KeyError as e:
                    print(f"Unexpected data structure: {e}")
                    print(f"Full data: {data}")
        else:
            raise Exception(f"Error: {response.status_code} - {response.text}")

    def get_completion(self, payload: dict) -> str:
        response = requests.post(self.url, headers=self.headers, json=payload)
        if response.status_code == 200:
            res = response.json()
            return res["choices"][0]["message"]["content"] if "choices" in res else ""
        else:
            raise Exception(f"Error: {response.status_code} - {response.text}")
