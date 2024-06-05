"""
title: Detoxify Filter Pipeline
author: open-webui
date: 2024-05-30
version: 1.0
license: MIT
description: A pipeline for filtering out toxic messages using the Detoxify library.
requirements: detoxify
"""

from typing import List, Optional
from schemas import OpenAIChatMessage
from pydantic import BaseModel
from detoxify import Detoxify
import os


class Pipeline:
    class Valves(BaseModel):
        # List target pipeline ids (models) that this filter will be connected to.
        # If you want to connect this filter to all pipelines, you can set pipelines to ["*"]
        # e.g. ["llama3:latest", "gpt-3.5-turbo"]
        pipelines: List[str] = []

        # Assign a priority level to the filter pipeline.
        # The priority level determines the order in which the filter pipelines are executed.
        # The lower the number, the higher the priority.
        priority: int = 0

    def __init__(self):
        # Pipeline filters are only compatible with Open WebUI
        # You can think of filter pipeline as a middleware that can be used to edit the form data before it is sent to the OpenAI API.
        self.type = "filter"

        # Optionally, you can set the id and name of the pipeline.
        # Best practice is to not specify the id so that it can be automatically inferred from the filename, so that users can install multiple versions of the same pipeline.
        # The identifier must be unique across all pipelines.
        # The identifier must be an alphanumeric string that can include underscores or hyphens. It cannot contain spaces, special characters, slashes, or backslashes.
        # self.id = "detoxify_filter_pipeline"
        self.name = "Detoxify Filter"

        # Initialize
        self.valves = self.Valves(
            **{
                "pipelines": ["*"],  # Connect to all pipelines
            }
        )

        self.model = None

        pass

    async def on_startup(self):
        # This function is called when the server is started.
        print(f"on_startup:{__name__}")

        self.model = Detoxify("original")
        pass

    async def on_shutdown(self):
        # This function is called when the server is stopped.
        print(f"on_shutdown:{__name__}")
        pass

    async def on_valves_updated(self):
        # This function is called when the valves are updated.
        pass

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        # This filter is applied to the form data before it is sent to the OpenAI API.
        print(f"inlet:{__name__}")

        print(body)
        user_message = body["messages"][-1]["content"]

        # Filter out toxic messages
        toxicity = self.model.predict(user_message)
        print(toxicity)

        if toxicity["toxicity"] > 0.5:
            raise Exception("Toxic message detected")

        return body
