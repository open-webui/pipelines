"""
title: Perplexity Pipeline
author: Seyed Yahya Shirazi
author_url: neuromechanist.github.io
date: 2024-11-19
version: 1.0
license: MIT
description: A pipeline for generating text using the Perplexity API.
requirements: requests, sseclient-py
environment_variables: PERPLEXITY_API_KEY
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
        PERPLEXITY_API_KEY: str = ""

    def __init__(self):
        self.type = "manifold"
        self.id = "perplexity_manifold"
        self.name = ""

        self.valves = self.Valves(
            **{"PERPLEXITY_API_KEY": os.getenv("PERPLEXITY_API_KEY", "your-api-key-here")}
        )
        self.url = 'https://api.perplexity.ai/chat/completions'
        self.update_headers()

    def update_headers(self):
        self.headers = {
            'Authorization': f'Bearer {self.valves.PERPLEXITY_API_KEY}',
            'Content-Type': 'application/json'
        }

    def get_perplexity_models(self):
        return [
            {
                "id": "llama-3.1-sonar-small-128k-online",
                "name": "Perplexity Llama 3.1 Sonar Small"
            },
            {
                "id": "llama-3.1-sonar-large-128k-online",
                "name": "Perplexity Llama 3.1 Sonar Large"
            },
            {
                "id": "llama-3.1-sonar-huge-128k-online",
                "name": "Perplexity Llama 3.1 Sonar Huge"
            },
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
        return self.get_perplexity_models()

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        try:
            # Remove unnecessary keys
            for key in ['user', 'chat_id', 'title']:
                body.pop(key, None)

            system_message, messages = pop_system_message(messages)

            # Add system message as the first message if present
            processed_messages = []
            if system_message:
                processed_messages.append({
                    "role": "system",
                    "content": str(system_message)
                })

            # Process remaining messages
            for message in messages:
                content = (
                    message["content"][0]["text"]
                    if isinstance(message["content"], list)
                    else message["content"]
                )
                processed_messages.append({
                    "role": message["role"],
                    "content": content
                })

            # Prepare the payload with Perplexity-specific parameters
            payload = {
                "model": model_id,
                "messages": processed_messages,
                "max_tokens": body.get("max_tokens", None),  # Optional in Perplexity
                "temperature": body.get("temperature", 0.2),  # Perplexity default
                "top_p": body.get("top_p", 0.9),  # Perplexity default
                "top_k": body.get("top_k", 0),    # Perplexity default
                "stream": body.get("stream", False),
                "presence_penalty": body.get("presence_penalty", 0),
                "frequency_penalty": body.get("frequency_penalty", 1),
            }

            # Add Perplexity-specific features if specified
            if "search_domain_filter" in body:
                payload["search_domain_filter"] = body["search_domain_filter"]
            if "return_images" in body:
                payload["return_images"] = body["return_images"]
            if "return_related_questions" in body:
                payload["return_related_questions"] = body["return_related_questions"]
            if "search_recency_filter" in body:
                payload["search_recency_filter"] = body["search_recency_filter"]

            if body.get("stream", False):
                return self.stream_response(payload)
            else:
                return self.get_completion(payload)
        except Exception as e:
            return f"Error: {e}"

    def format_response_with_citations(self, content: str, citations: List[str]) -> str:
        """Format the response by appending citations at the end."""
        if not citations:
            return content

        # Content already contains [1], [2], etc. references
        formatted_response = content + "\n\nReferences:\n"
        for i, url in enumerate(citations, 1):
            formatted_response += f"[{i}] {url}\n"
        return formatted_response

    def stream_response(self, payload: dict) -> Generator:
        response = requests.post(self.url, headers=self.headers, json=payload, stream=True)
        accumulated_content = ""

        if response.status_code == 200:
            client = sseclient.SSEClient(response)
            citations = None
            for event in client.events():
                try:
                    data = json.loads(event.data)
                    if "citations" in data:
                        citations = data["citations"]
                    if data["choices"][0]["finish_reason"] is None:
                        content = data["choices"][0]["delta"]["content"]
                        accumulated_content += content
                        yield content
                    elif data["choices"][0]["finish_reason"] == "stop" and citations:
                        yield "\n\nReferences:\n" + "\n".join(
                            f"[{i}] {url}" for i, url in enumerate(citations, 1)
                        )
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
            content = res["choices"][0]["message"]["content"]
            citations = res.get("citations", [])
            return self.format_response_with_citations(content, citations)
        else:
            raise Exception(f"Error: {response.status_code} - {response.text}")
