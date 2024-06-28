"""
title: Google GenAI Manifold Pipeline
author: Marc Lopez
date: 2024-06-06
version: 1.1
license: MIT
description: A pipeline for generating text using Google's GenAI models in Open-WebUI.
requirements: google-generativeai
environment_variables: GOOGLE_API_KEY
"""

from typing import List, Union, Iterator
import os

from pydantic import BaseModel

import google.generativeai as genai


class Pipeline:
    """Google GenAI pipeline"""

    class Valves(BaseModel):
        """Options to change from the WebUI"""

        GOOGLE_API_KEY: str = ""

    def __init__(self):
        self.type = "manifold"
        self.id = "google_genai"
        self.name = "Google: "

        self.valves = self.Valves(**{"GOOGLE_API_KEY": os.getenv("GOOGLE_API_KEY", "")})
        self.pipelines = []

        genai.configure(api_key=self.valves.GOOGLE_API_KEY)
        self.update_pipelines()

    async def on_startup(self) -> None:
        """This function is called when the server is started."""

        print(f"on_startup:{__name__}")

    async def on_shutdown(self) -> None:
        """This function is called when the server is stopped."""

        print(f"on_shutdown:{__name__}")

    async def on_valves_updated(self) -> None:
        """This function is called when the valves are updated."""

        print(f"on_valves_updated:{__name__}")
        genai.configure(api_key=self.valves.GOOGLE_API_KEY)
        self.update_pipelines()

    def update_pipelines(self) -> None:
        """Update the available models from Google GenAI"""

        if self.valves.GOOGLE_API_KEY:
            try:
                models = genai.list_models()
                self.pipelines = [
                    {
                        "id": model.name[7:],  # the "models/" part messeses up the URL
                        "name": model.display_name,
                    }
                    for model in models
                    if "generateContent" in model.supported_generation_methods
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
        print(f"Pipe function called for model: {model_id}")
        print(f"Stream mode: {body['stream']}")

        system_prompt = None
        google_messages = []

        for message in messages:
            if message["role"] == "system":
                system_prompt = message["content"]
                continue

            google_role = "user" if message["role"] == "user" else "model"
            
            try:
                content = message.get("content", "")
                if isinstance(content, list):
                    parts = []
                    for item in content:
                        if item["type"] == "text":
                            parts.append({"text": item["text"]})
                else:
                    parts = [{"text": content}]

                google_messages.append({
                    "role": google_role,
                    "parts": parts
                })
            except Exception as e:
                print(f"Error processing message: {e}")
                print(f"Problematic message: {message}")

        try:
            model = genai.GenerativeModel(
                f"models/{model_id}",
                generation_config=genai.GenerationConfig(
                    temperature=body.get("temperature", 0.7),
                    top_p=body.get("top_p", 1.0),
                    top_k=body.get("top_k", 1),
                    max_output_tokens=body.get("max_tokens", 1024),
                )
            )

            response = model.generate_content(
                google_messages,
                stream=body["stream"],
            )

            if body["stream"]:
                print("Streaming response")
                return (chunk.text for chunk in response)
            else:
                print("Non-streaming response")
                result = response.text
                print(f"Generated content: {result}")
                return result

        except Exception as e:
            print(f"Error generating content: {e}")
            return f"An error occurred: {str(e)}"

        finally:
            print("Pipe function completed")
