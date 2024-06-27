"""
title: Anthropic Manifold Pipeline
author: justinh-rahb
date: 2024-06-20
version: 1.3
license: MIT
description: A pipeline for generating text and processing images using the Anthropic API.
requirements: requests, anthropic
environment_variables: ANTHROPIC_API_KEY
"""

import os
from anthropic import Anthropic, RateLimitError, APIStatusError, APIConnectionError

from schemas import OpenAIChatMessage
from typing import List, Union, Generator, Iterator
from pydantic import BaseModel
import requests

from utils.pipelines.main import pop_system_message


class Pipeline:
    class Valves(BaseModel):
        ANTHROPIC_API_KEY: str = ""

    def __init__(self):
        self.type = "manifold"
        self.id = "anthropic"
        self.name = "anthropic/"

        self.valves = self.Valves(
            **{"ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY", "your-api-key-here")}
        )
        self.client = Anthropic(api_key=self.valves.ANTHROPIC_API_KEY)

    def get_anthropic_models(self):
        return [
            {"id": "claude-3-haiku-20240307", "name": "claude-3-haiku"},
            {"id": "claude-3-opus-20240229", "name": "claude-3-opus"},
            {"id": "claude-3-sonnet-20240229", "name": "claude-3-sonnet"},
            {"id": "claude-3-5-sonnet-20240620", "name": "claude-3.5-sonnet"},
        ]

    async def on_startup(self):
        print(f"on_startup:{__name__}")
        pass

    async def on_shutdown(self):
        print(f"on_shutdown:{__name__}")
        pass

    async def on_valves_updated(self):
        self.client = Anthropic(api_key=self.valves.ANTHROPIC_API_KEY)
        pass

    def pipelines(self) -> List[dict]:
        return self.get_anthropic_models()

    def process_image(self, image_data):
        if image_data["url"].startswith("data:image"):
            mime_type, base64_data = image_data["url"].split(",", 1)
            media_type = mime_type.split(":")[1].split(";")[0]
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64_data,
                },
            }
        else:
            return {
                "type": "image",
                "source": {"type": "url", "url": image_data["url"]},
            }

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        try:
            # Remove unnecessary keys
            for key in ['user', 'chat_id', 'title']:
                body.pop(key, None)

            system_message, messages = pop_system_message(messages)

            processed_messages = []
            image_count = 0
            total_image_size = 0

            for message in messages:
                processed_content = []
                if isinstance(message.get("content"), list):
                    for item in message["content"]:
                        if item["type"] == "text":
                            processed_content.append({"type": "text", "text": item["text"]})
                        elif item["type"] == "image_url":
                            if image_count >= 5:
                                raise ValueError("Maximum of 5 images per API call exceeded")

                            processed_image = self.process_image(item["image_url"])
                            processed_content.append(processed_image)

                            if processed_image["source"]["type"] == "base64":
                                image_size = len(processed_image["source"]["data"]) * 3 / 4
                            else:
                                image_size = 0

                            total_image_size += image_size
                            if total_image_size > 100 * 1024 * 1024:
                                raise ValueError("Total size of images exceeds 100 MB limit")

                            image_count += 1
                else:
                    processed_content = [{"type": "text", "text": message.get("content", "")}]

                processed_messages.append({"role": message["role"], "content": processed_content})

            # Prepare the payload
            payload = {
                "model": model_id,
                "messages": processed_messages,
                "max_tokens": body.get("max_tokens", 4096),
                "temperature": body.get("temperature", 0.8),
                "top_k": body.get("top_k", 40),
                "top_p": body.get("top_p", 0.9),
                "stop_sequences": body.get("stop", []),
                **({"system": str(system_message)} if system_message else {}),
                "stream": body.get("stream", False),
            }

            if body.get("stream", False):
                return self.stream_response(model_id, payload)
            else:
                return self.get_completion(model_id, payload)
        except (RateLimitError, APIStatusError, APIConnectionError) as e:
            return f"Error: {e}"

    def stream_response(self, model_id: str, payload: dict) -> Generator:
        stream = self.client.messages.create(**payload)

        for chunk in stream:
            if chunk.type == "content_block_start":
                yield chunk.content_block.text
            elif chunk.type == "content_block_delta":
                yield chunk.delta.text

    def get_completion(self, model_id: str, payload: dict) -> str:
        response = self.client.messages.create(**payload)
        return response.content[0].text