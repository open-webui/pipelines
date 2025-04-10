"""
title: Google GenAI Manifold Pipeline
author: Marc Lopez (refactor by justinh-rahb)
date: 2024-06-06
version: 1.3
license: MIT
description: A pipeline for generating text using Google's GenAI models in Open-WebUI.
requirements: google-genai
environment_variables: GOOGLE_API_KEY
"""

from typing import List, Union, Iterator
import os

from pydantic import BaseModel, Field

from google import genai
from google.genai import types
from PIL import Image
from io import BytesIO
import base64


class Pipeline:
    """Google GenAI pipeline"""

    class Valves(BaseModel):
        """Options to change from the WebUI"""

        GOOGLE_API_KEY: str = Field(default="",description="Google Generative AI API key")
        USE_PERMISSIVE_SAFETY: bool = Field(default=False,description="Use permissive safety settings")
        GENERATE_IMAGE: bool = Field(default=False,description="Allow image generation")

    def __init__(self):
        self.type = "manifold"
        self.id = "google_genai"
        self.name = "Google: "

        self.valves = self.Valves(**{
            "GOOGLE_API_KEY": os.getenv("GOOGLE_API_KEY", ""),
            "USE_PERMISSIVE_SAFETY": False,
            "GENERATE_IMAGE": False
        })
        self.pipelines = []

        if self.valves.GOOGLE_API_KEY:
            self.update_pipelines()

    async def on_startup(self) -> None:
        """This function is called when the server is started."""

        print(f"on_startup:{__name__}")
        if self.valves.GOOGLE_API_KEY:
            self.update_pipelines()

    async def on_shutdown(self) -> None:
        """This function is called when the server is stopped."""

        print(f"on_shutdown:{__name__}")

    async def on_valves_updated(self) -> None:
        """This function is called when the valves are updated."""

        print(f"on_valves_updated:{__name__}")
        if self.valves.GOOGLE_API_KEY:
            self.update_pipelines()

    def update_pipelines(self) -> None:
        """Update the available models from Google GenAI"""

        if self.valves.GOOGLE_API_KEY:
            client = genai.Client(api_key=self.valves.GOOGLE_API_KEY)
            try:
                models = client.models.list()
                self.pipelines = [
                    {
                        "id": model.name[7:],  # the "models/" part messeses up the URL
                        "name": model.display_name,
                    }
                    for model in models
                    if "generateContent" in model.supported_actions
                    if model.name[:7] == "models/"
                ]
            except Exception:
                self.pipelines = [
                    {
                        "id": "error",
                        "name": "Could not fetch models from Google, please update the API Key in the valves.",
                    }
                ]
        else:
            self.pipelines = []

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Iterator]:
        if not self.valves.GOOGLE_API_KEY:
            return "Error: GOOGLE_API_KEY is not set"

        try:
            client = genai.Client(api_key=self.valves.GOOGLE_API_KEY)

            if model_id.startswith("google_genai."):
                model_id = model_id[12:]
            model_id = model_id.lstrip(".")

            if not (model_id.startswith("gemini-") or model_id.startswith("learnlm-") or model_id.startswith("gemma-")):
                return f"Error: Invalid model name format: {model_id}"

            print(f"Pipe function called for model: {model_id}")
            print(f"Stream mode: {body.get('stream', False)}")

            system_message = next((msg["content"] for msg in messages if msg["role"] == "system"), None)
            
            contents = []
            for message in messages:
                if message["role"] != "system":
                    if isinstance(message.get("content"), list):
                        parts = []
                        for content in message["content"]:
                            if content["type"] == "text":
                                parts.append({"text": content["text"]})
                            elif content["type"] == "image_url":
                                image_url = content["image_url"]["url"]
                                if image_url.startswith("data:image"):
                                    image_data = image_url.split(",")[1]
                                    parts.append({"inline_data": {"mime_type": "image/jpeg", "data": image_data}})
                                else:
                                    parts.append({"image_url": image_url})
                        contents.append({"role": message["role"], "parts": parts})
                    else:
                        contents.append({
                            "role": "user" if message["role"] == "user" else "model",
                            "parts": [{"text": message["content"]}]
                        })
            print(f"{contents}")

            generation_config = {
                "temperature": body.get("temperature", 0.7),
                "top_p": body.get("top_p", 0.9),
                "top_k": body.get("top_k", 40),
                "max_output_tokens": body.get("max_tokens", 8192),
                "stop_sequences": body.get("stop", []),
                "response_modalities": ['Text']
            }

            if self.valves.GENERATE_IMAGE and model_id.startswith("gemini-2.0-flash-exp"):
                generation_config["response_modalities"].append("Image")

            if self.valves.USE_PERMISSIVE_SAFETY:
                safety_settings = [
                    types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='OFF'),
                    types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='OFF'),
                    types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='OFF'),
                    types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='OFF'),
                    types.SafetySetting(category='HARM_CATEGORY_CIVIC_INTEGRITY', threshold='OFF')
                ]
                generation_config = types.GenerateContentConfig(**generation_config, safety_settings=safety_settings)
            else:
                generation_config = types.GenerateContentConfig(**generation_config)

            if system_message:
                contents.insert(0, {"role": "user", "parts": [{"text": f"System: {system_message}"}]})

            if body.get("stream", False):
                response = client.models.generate_content_stream(
                    model = model_id,
                    contents = contents,
                    config = generation_config,
                )
                return self.stream_response(response)
            else:
                response = client.models.generate_content(
                    model = model_id,
                    contents = contents,
                    config = generation_config,
                )
                for part in response.candidates[0].content.parts:
                    if part.text is not None:
                        return part.text
                    elif part.inline_data is not None:
                        try:
                            image_data = base64.b64decode(part.inline_data.data)
                            image = Image.open(BytesIO((image_data)))
                            content_type = part.inline_data.mime_type
                            return "Image not supported yet."
                        except Exception as e:
                            print(f"Error processing image: {e}")
                            return "Error processing image."

        except Exception as e:
            print(f"Error generating content: {e}")
            return f"{e}"

    def stream_response(self, response):
        for chunk in response:
            for candidate in chunk.candidates:
                if candidate.content.parts is not None:
                    for part in candidate.content.parts:
                        if part.text is not None:
                            yield chunk.text
                        elif part.inline_data is not None:
                            try:
                                image_data = base64.b64decode(part.inline_data.data)
                                image = Image.open(BytesIO(image_data))
                                content_type = part.inline_data.mime_type
                                yield "Image not supported yet."
                            except Exception as e:
                                print(f"Error processing image: {e}")
                                yield "Error processing image."
