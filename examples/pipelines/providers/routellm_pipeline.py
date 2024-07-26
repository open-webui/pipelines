"""
title: RouteLLM Pipeline
author: justinh-rahb
date: 2024-07-25
version: 0.2.0
license: MIT
description: A pipeline for routing LLM requests using RouteLLM framework, compatible with OpenAI API.
requirements: routellm, pydantic, requests
"""

from typing import List, Union, Generator, Iterator
from pydantic import BaseModel, Field
import logging
from routellm.controller import Controller

class Pipeline:
    class Valves(BaseModel):
        ROUTELLM_ROUTER: str = Field(
            default="mf", description="Identifier for the RouteLLM router."
        )
        ROUTELLM_STRONG_MODEL: str = Field(
            default="gpt-4o", description="Identifier for the strong model."
        )
        ROUTELLM_WEAK_MODEL: str = Field(
            default="gpt-4o-mini", description="Identifier for the weak model."
        )
        ROUTELLM_STRONG_API_KEY: str = Field(
            default="sk-your-api-key",
            description="API key for accessing the strong model."
        )
        ROUTELLM_WEAK_API_KEY: str = Field(
            default="sk-your-api-key",
            description="API key for accessing the weak model."
        )
        ROUTELLM_STRONG_BASE_URL: str = Field(
            default="https://api.openai.com/v1",
            description="Base URL for the strong model's API."
        )
        ROUTELLM_WEAK_BASE_URL: str = Field(
            default="https://api.openai.com/v1",
            description="Base URL for the weak model's API."
        )
        ROUTELLM_THRESHOLD: float = Field(
            default=0.11593,
            description="Threshold value for determining when to use the strong model."
        )
        ROUTELLM_SUFFIX: str = Field(
            default="OpenAI",
            description="Suffix to use for model identifier and name."
        )

    def __init__(self):
        self.type = "manifold"
        self.valves = self.Valves()
        self.id = "routellm"
        self.name = f"RouteLLM/"
        self.controller = None
        
        self._initialize_controller()

    def pipelines(self) -> List[dict]:
        return [{"id": f"{self.valves.ROUTELLM_SUFFIX.lower()}", "name": f"{self.valves.ROUTELLM_SUFFIX}"}]

    async def on_startup(self):
        logging.info(f"on_startup: {__name__}")

    async def on_shutdown(self):
        logging.info(f"on_shutdown: {__name__}")

    async def on_valves_updated(self):
        logging.info(f"on_valves_updated: {__name__}")
        self._initialize_controller()

    def _initialize_controller(self):
        try:
            strong_model = self.valves.ROUTELLM_STRONG_MODEL
            weak_model = self.valves.ROUTELLM_WEAK_MODEL

            # Set the API keys as environment variables
            import os
            os.environ["OPENAI_API_KEY"] = self.valves.ROUTELLM_STRONG_API_KEY

            self.controller = Controller(
                routers=[self.valves.ROUTELLM_ROUTER],
                strong_model=strong_model,
                weak_model=weak_model
            )
            logging.info("RouteLLM controller initialized successfully")
        except Exception as e:
            logging.error(f"Error initializing RouteLLM controller: {e}")
            self.controller = None

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        if not self.controller:
            return "Error: RouteLLM controller not initialized. Please update valves with valid API keys and configuration."

        try:
            model_name = f"router-{self.valves.ROUTELLM_ROUTER}-{self.valves.ROUTELLM_THRESHOLD}"
            
            # Prepare parameters, excluding 'model' and 'messages' if they're in body
            params = {k: v for k, v in body.items() if k not in ['model', 'messages'] and v is not None}

            response = self.controller.completion(
                model=model_name,
                messages=messages,
                **params
            )
            
            if body.get("stream", False):
                return (chunk for chunk in response)
            else:
                return response
        except Exception as e:
            logging.error(f"Error in pipe: {e}")
            return f"Error: {e}"
