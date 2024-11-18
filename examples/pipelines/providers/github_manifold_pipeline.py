"""
title: Github Models Manifold Pipeline
author: cheahjs, (working pipeline by HomeDev68)
author_url: https://github.com/cheahjs, https://github.com/HomeDev68
date: 2024-10-19
version: 1.2
license: MIT
description: A pipeline for generating text using Github Marketplace Models in Open-WebUI.
environment_variables: GITHUB_PAT
"""

from typing import List, Union, Generator, Iterator
from schemas import OpenAIChatMessage
from pydantic import BaseModel

import os
import requests


class Pipeline:
    """Github Models Pipeline"""

    class Valves(BaseModel):
        """Options to change from the WebUI"""

        GITHUB_MODELS_BASE_URL: str = "https://models.inference.ai.azure.com"
        GITHUB_PAT: str = ""
        
    def __init__(self):
        # Optionally, you can set the id and name of the pipeline.
        # Best practice is to not specify the id so that it can be automatically inferred from the filename, so that users can install multiple versions of the same pipeline.
        # The identifier must be unique across all pipelines.
        # The identifier must be an alphanumeric string that can include underscores or hyphens. It cannot contain spaces, special characters, slashes, or backslashes.
        self.type = "manifold"
        self.id = "github_models"
        self.name = "GitHub: "

        self.valves = self.Valves(
            **{
                "GITHUB_MODELS_BASE_URL": os.getenv("GITHUB_MODELS_BASE_URL","https://models.inference.ai.azure.com"),
                "GITHUB_PAT": os.getenv("GITHUB_PAT", "")                
            }
        )

        self.pipelines = self.get_github_models()
        
    
    async def on_startup(self):
        # This function is called when the server is started.
        print(f"on_startup:{__name__}")
        pass

    async def on_shutdown(self):
        # This function is called when the server is stopped.
        print(f"on_shutdown:{__name__}")
        pass

    async def on_valves_updated(self):
        # This function is called when the valves are updated.
        print(f"on_valves_updated:{__name__}")
        self.pipelines = self.get_github_models()
        pass

    def get_github_models(self):
        """Gets Available Github Models"""
        if self.valves.GITHUB_PAT:
            try:
                headers = {}
                headers["Authorization"] = f"Bearer {self.valves.GITHUB_PAT}"
                headers["Content-Type"] = "application/json"

                r = requests.get(f"{self.valves.GITHUB_MODELS_BASE_URL}/models", headers=headers)
                models = r.json()
                # Parse the json according to keys, since the json output is too large
                return [
                    {
                        "id": model["name"],
                        "name": (
                            model["friendly_name"]
                            if "friendly_name" in model
                            else model["name"]
                        ),
                        "description": (model["summary"] if "summary" in model else ""),
                    }
                    for model in models
                    if model["task"] == "chat-completion"
                ]
            except Exception as e:

                print(f"Error: {e}")
                return [
                    {
                        "id": "error",
                        "name": "Could not fetch models from GitHub Models, please update the PAT in the valves.",
                    },
                ]
        else:
            return []

    def pipe(self, user_message: str, model_id: str, messages: List[dict], body: dict) -> Union[str, Generator, Iterator]:
        # This is where you can add your custom pipelines like RAG.
        print(f"pipe:{__name__}")

        # Log the messages for debugging
        print(messages)
        print(user_message)

        headers = {}
        headers["Authorization"] = f"Bearer {self.valves.GITHUB_PAT}"
        headers["Content-Type"] = "application/json"

        allowed_params = {"messages", "temperature", "top_p", "stream", "stop", "model", "max_tokens", "stream_options" }
        
        # Remap the model name to the model id
        body["model"] = ".".join(body["model"].split(".")[1:])
        filtered_body = {k: v for k, v in body.items() if k in allowed_params}

        # log fields that were filtered out as a single line
        if len(body) != len(filtered_body):
            print(f"Dropped params: {', '.join(set(body.keys()) - set(filtered_body.keys()))}")
            
        # Initialize the response variable to None.
        r = None
        try:
            r = requests.post(
                url=f"{self.valves.GITHUB_MODELS_BASE_URL}/chat/completions",
                json=filtered_body,
                headers=headers,
                stream=True,
            )

            r.raise_for_status()
            if body["stream"]:
                return r.iter_lines()
            else:
                return r.json()
        except Exception as e:
            # TODO: Render Errors Normally in Open-WebUI, not in the message body
            print(f"Error generating content: {e}")
            return f"Error: {str(e)}"
