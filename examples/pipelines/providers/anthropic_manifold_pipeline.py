"""
title: Anthropic Manifold Pipeline
author: justinh-rahb, sriparashiva
date: 2024-06-20
version: 1.4
license: MIT
description: A pipeline for generating text and processing images using the Anthropic API.
requirements: requests, sseclient-py
environment_variables: ANTHROPIC_API_KEY, ANTHROPIC_THINKING_BUDGET_TOKENS, ANTHROPIC_ENABLE_THINKING
"""

import os
import requests
import json
from typing import List, Union, Generator, Iterator
from pydantic import BaseModel
import sseclient

from utils.pipelines.main import pop_system_message

REASONING_EFFORT_BUDGET_TOKEN_MAP = {
    "none": None,
    "low": 1024,
    "medium": 4096,
    "high": 16384,
    "max": 32768,
}

# Maximum combined token limit for Claude 3.7
MAX_COMBINED_TOKENS = 64000


class Pipeline:
    class Valves(BaseModel):
        ANTHROPIC_API_KEY: str = ""

    def __init__(self):
        self.type = "manifold"
        self.id = "anthropic"
        self.name = "anthropic/"

        self.valves = self.Valves(
            **{
                "ANTHROPIC_API_KEY": os.getenv(
                    "ANTHROPIC_API_KEY", "your-api-key-here"
                ),
            }
        )
        self.url = "https://api.anthropic.com/v1/messages"
        self.update_headers()

    def update_headers(self):
        self.headers = {
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "x-api-key": self.valves.ANTHROPIC_API_KEY,
        }

    def get_anthropic_models(self):
        return [
            {"id": "claude-3-haiku-20240307", "name": "claude-3-haiku"},
            {"id": "claude-3-opus-20240229", "name": "claude-3-opus"},
            {"id": "claude-3-sonnet-20240229", "name": "claude-3-sonnet"},
            {"id": "claude-3-5-haiku-20241022", "name": "claude-3.5-haiku"},
            {"id": "claude-3-5-sonnet-20241022", "name": "claude-3.5-sonnet"},
            {"id": "claude-3-7-sonnet-20250219", "name": "claude-3.7-sonnet"},
            {"id": "claude-opus-4-20250514", "name": "claude-4-opus"},
            {"id": "claude-sonnet-4-20250514", "name": "claude-4-sonnet"},
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
            for key in ["user", "chat_id", "title"]:
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
                            processed_content.append(
                                {"type": "text", "text": item["text"]}
                            )
                        elif item["type"] == "image_url":
                            if image_count >= 5:
                                raise ValueError(
                                    "Maximum of 5 images per API call exceeded"
                                )

                            processed_image = self.process_image(item["image_url"])
                            processed_content.append(processed_image)

                            if processed_image["source"]["type"] == "base64":
                                image_size = (
                                    len(processed_image["source"]["data"]) * 3 / 4
                                )
                            else:
                                image_size = 0

                            total_image_size += image_size
                            if total_image_size > 100 * 1024 * 1024:
                                raise ValueError(
                                    "Total size of images exceeds 100 MB limit"
                                )

                            image_count += 1
                else:
                    processed_content = [
                        {"type": "text", "text": message.get("content", "")}
                    ]

                processed_messages.append(
                    {"role": message["role"], "content": processed_content}
                )

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
                supports_thinking = "claude-3-7" in model_id
                reasoning_effort = body.get("reasoning_effort", "none")
                budget_tokens = REASONING_EFFORT_BUDGET_TOKEN_MAP.get(reasoning_effort)

                # Allow users to input an integer value representing budget tokens
                if (
                    not budget_tokens
                    and reasoning_effort is not None
                    and reasoning_effort not in REASONING_EFFORT_BUDGET_TOKEN_MAP.keys()
                ):
                    try:
                        budget_tokens = int(reasoning_effort)
                    except ValueError as e:
                        print("Failed to convert reasoning effort to int", e)
                        budget_tokens = None

                if supports_thinking and budget_tokens:
                    # Check if the combined tokens (budget_tokens + max_tokens) exceeds the limit
                    max_tokens = payload.get("max_tokens", 4096)
                    combined_tokens = budget_tokens + max_tokens

                    if combined_tokens > MAX_COMBINED_TOKENS:
                        error_message = f"Error: Combined tokens (budget_tokens {budget_tokens} + max_tokens {max_tokens} = {combined_tokens}) exceeds the maximum limit of {MAX_COMBINED_TOKENS}"
                        print(error_message)
                        return error_message

                    payload["max_tokens"] = combined_tokens
                    payload["thinking"] = {
                        "type": "enabled",
                        "budget_tokens": budget_tokens,
                    }
                    # Thinking requires temperature 1.0 and does not support top_p, top_k
                    payload["temperature"] = 1.0
                    if "top_k" in payload:
                        del payload["top_k"]
                    if "top_p" in payload:
                        del payload["top_p"]
                return self.stream_response(payload)
            else:
                return self.get_completion(payload)
        except Exception as e:
            return f"Error: {e}"

    def stream_response(self, payload: dict) -> Generator:
        """Used for title and tag generation"""
        try:
            response = requests.post(
                self.url, headers=self.headers, json=payload, stream=True
            )
            print(f"{response} for {payload}")

            if response.status_code == 200:
                client = sseclient.SSEClient(response)
                for event in client.events():
                    try:
                        data = json.loads(event.data)
                        if data["type"] == "content_block_start":
                            if data["content_block"]["type"] == "thinking":
                                yield "<think>"
                            else:
                                yield data["content_block"]["text"]
                        elif data["type"] == "content_block_delta":
                            if data["delta"]["type"] == "thinking_delta":
                                yield data["delta"]["thinking"]
                            elif data["delta"]["type"] == "signature_delta":
                                yield "\n </think> \n\n"
                            else:
                                yield data["delta"]["text"]
                        elif data["type"] == "message_stop":
                            break
                    except json.JSONDecodeError:
                        print(f"Failed to parse JSON: {event.data}")
                        yield f"Error: Failed to parse JSON response"
                    except KeyError as e:
                        print(f"Unexpected data structure: {e} for payload {payload}")
                        print(f"Full data: {data}")
                        yield f"Error: Unexpected data structure: {e}"
            else:
                error_message = f"Error: {response.status_code} - {response.text}"
                print(error_message)
                yield error_message
        except Exception as e:
            error_message = f"Error: {str(e)}"
            print(error_message)
            yield error_message

    def get_completion(self, payload: dict) -> str:
        try:
            response = requests.post(self.url, headers=self.headers, json=payload)
            print(response, payload)
            if response.status_code == 200:
                res = response.json()
                for content in res["content"]:
                    if not content.get("text"):
                        continue
                    return content["text"]
                return ""
            else:
                error_message = f"Error: {response.status_code} - {response.text}"
                print(error_message)
                return error_message
        except Exception as e:
            error_message = f"Error: {str(e)}"
            print(error_message)
            return error_message
