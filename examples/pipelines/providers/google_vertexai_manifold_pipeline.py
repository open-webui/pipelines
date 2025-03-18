"""
title: Google GenAI (Vertex AI) Manifold Pipeline
author: Hiromasa Kakehashi
date: 2024-09-19
version: 1.0
license: MIT
description: A pipeline for generating text using Google's GenAI models in Open-WebUI.
requirements: vertexai
environment_variables: GOOGLE_PROJECT_ID, GOOGLE_CLOUD_REGION
usage_instructions:
  To use Gemini with the Vertex AI API, a service account with the appropriate role (e.g., `roles/aiplatform.user`) is required.
  - For deployment on Google Cloud: Associate the service account with the deployment.
  - For use outside of Google Cloud: Set the GOOGLE_APPLICATION_CREDENTIALS environment variable to the path of the service account key file.
"""

import os
from typing import Iterator, List, Union

import vertexai
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from vertexai.generative_models import (Content, GenerationConfig,
                                        GenerativeModel, HarmBlockThreshold,
                                        HarmCategory, Part)


class Pipeline:
    """Google GenAI pipeline"""

    class Valves(BaseModel):
        """Options to change from the WebUI"""

        GOOGLE_PROJECT_ID: str = ""
        GOOGLE_CLOUD_REGION: str = ""
        USE_PERMISSIVE_SAFETY: bool = Field(default=False)

    def __init__(self):
        self.type = "manifold"
        self.name = "vertexai: "

        self.valves = self.Valves(
            **{
                "GOOGLE_PROJECT_ID": os.getenv("GOOGLE_PROJECT_ID", ""),
                "GOOGLE_CLOUD_REGION": os.getenv("GOOGLE_CLOUD_REGION", ""),
                "GOOGLE_APPLICATION_CREDENTIALS": os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
                "USE_PERMISSIVE_SAFETY": False,
            }
        )
        self.pipelines = [
            {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash"},
            {"id": "gemini-2.0-flash-lite-preview-02-05", "name": "Gemini 2.0 Flash Lite"},
            {"id": "gemini-2.0-pro-exp-02-05", "name": "Gemini 2.0 Pro"},
            {"id": "gemini-2.0-flash-thinking-exp-01-21", "name": "Gemini 2.0 Flash Thinking"},
        ]

    async def on_startup(self) -> None:
        """This function is called when the server is started."""

        print(f"on_startup:{__name__}")
        vertexai.init(
            project=self.valves.GOOGLE_PROJECT_ID,
            location=self.valves.GOOGLE_CLOUD_REGION,
        )

    async def on_shutdown(self) -> None:
        """This function is called when the server is stopped."""
        print(f"on_shutdown:{__name__}")

    async def on_valves_updated(self) -> None:
        """This function is called when the valves are updated."""
        print(f"on_valves_updated:{__name__}")
        vertexai.init(
            project=self.valves.GOOGLE_PROJECT_ID,
            location=self.valves.GOOGLE_CLOUD_REGION,
        )

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Iterator]:
        try:
            if not model_id.startswith("gemini-"):
                return f"Error: Invalid model name format: {model_id}"

            print(f"Pipe function called for model: {model_id}")
            print(f"Stream mode: {body.get('stream', False)}")

            system_message = next(
                (msg["content"] for msg in messages if msg["role"] == "system"), None
            )

            client = genai.Client(
                vertexai=True,
                project=self.valves.GOOGLE_PROJECT_ID,
                location=self.valves.GOOGLE_CLOUD_REGION,
            )

            contents = [
                types.Content(
                    role="user",
                    parts=[types.Part(text=user_message)]
                )
            ]

            generate_content_config = types.GenerateContentConfig(
                temperature=body.get("temperature", 0.7),
                top_p=body.get("top_p", 0.95),
                max_output_tokens=body.get("max_tokens", 8192),
                response_modalities=["TEXT"],
                safety_settings=[
                    types.SafetySetting(
                        category="HARM_CATEGORY_HATE_SPEECH",
                        threshold="OFF"
                    ),
                    types.SafetySetting(
                        category="HARM_CATEGORY_DANGEROUS_CONTENT",
                        threshold="OFF"
                    ),
                    types.SafetySetting(
                        category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        threshold="OFF"
                    ),
                    types.SafetySetting(
                        category="HARM_CATEGORY_HARASSMENT",
                        threshold="OFF"
                    )
                ],
            )

            is_streaming = body.get("stream", False)
            try:
                response = client.models.generate_content_stream(
                    model=model_id,
                    contents=contents,
                    config=generate_content_config,
                )

                if is_streaming:
                    def stream_chunks():
                        try:
                            for chunk in response:
                                if chunk and chunk.text:
                                    yield chunk.text
                        except Exception as e:
                            print(f"Streaming error: {e}")
                            yield f"Error during streaming: {str(e)}"
                    
                    return stream_chunks()
                else:
                    return ''.join(chunk.text for chunk in response)

            except Exception as e:
                error_msg = f"Generation error: {str(e)}"
                print(error_msg)
                return error_msg

        except Exception as e:
            error_msg = f"Pipeline error: {str(e)}"
            print(error_msg)
            return error_msg

    def stream_response(self, response):
        try:
            for chunk in response:
                if chunk and chunk.text:
                    print(f"Chunk: {chunk.text}")
                    yield chunk.text
        except Exception as e:
            print(f"Stream response error: {e}")
            yield f"Error during streaming: {str(e)}"

    def build_conversation_history(self, messages: List[dict]) -> List[Content]:
        contents = []

        for message in messages:
            if message["role"] == "system":
                continue

            parts = []

            if isinstance(message.get("content"), list):
                for content in message["content"]:
                    if content["type"] == "text":
                        parts.append(Part.from_text(content["text"]))
                    elif content["type"] == "image_url":
                        image_url = content["image_url"]["url"]
                        if image_url.startswith("data:image"):
                            image_data = image_url.split(",")[1]
                            parts.append(Part.from_image(image_data))
                        else:
                            parts.append(Part.from_uri(image_url))
            else:
                parts = [Part.from_text(message["content"])]

            role = "user" if message["role"] == "user" else "model"
            contents.append(Content(role=role, parts=parts))

        return contents