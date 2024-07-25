"""
title: RouteLLM Pipeline
author: justinh-rahb
date: 2024-07-25
version: 0.1.0
license: MIT
description: A pipeline for routing LLM requests using RouteLLM framework, compatible with OpenAI API.
requirements: routellm, pydantic, requests
"""

from typing import List, Union, Generator, Iterator
from pydantic import BaseModel
import os
import logging
from routellm.controller import Controller

class Pipeline:
    class Valves(BaseModel):
        ROUTELLM_ROUTER: str = "mf"
        ROUTELLM_STRONG_MODEL: str = "gpt-4o"
        ROUTELLM_WEAK_MODEL: str = "gpt-4o-mini"
        ROUTELLM_STRONG_API_KEY: str = "sk-your-api-key"
        ROUTELLM_WEAK_API_KEY: str = "sk-your-api-key"
        ROUTELLM_STRONG_BASE_URL: str = "https://api.openai.com/v1"
        ROUTELLM_WEAK_BASE_URL: str = "https://api.openai.com/v1"
        ROUTELLM_THRESHOLD: float = 0.11593

    def __init__(self):
        self.id = "routellm"
        self.name = "RouteLLM"
        self.valves = self.Valves()
        self.controller = None
        
        # Set the environment variables for API keys and base URLs
        self._set_environment_variables()
        
        self._initialize_controller()

    def _set_environment_variables(self):
        os.environ["OPENAI_API_KEY"] = self.valves.ROUTELLM_STRONG_API_KEY
        logging.info(f"Setting OPENAI_API_KEY to: {os.environ['OPENAI_API_KEY']}")
        
        os.environ["WEAK_MODEL_API_KEY"] = self.valves.ROUTELLM_WEAK_API_KEY
        logging.info(f"Setting WEAK_MODEL_API_KEY to: {os.environ['WEAK_MODEL_API_KEY']}")

        if self.valves.ROUTELLM_STRONG_BASE_URL:
            os.environ['OPENAI_BASE_URL'] = self.valves.ROUTELLM_STRONG_BASE_URL
            logging.info(f"Setting OPENAI_BASE_URL to: {os.environ['OPENAI_BASE_URL']}")

        if self.valves.ROUTELLM_WEAK_BASE_URL:
            os.environ['WEAK_MODEL_BASE_URL'] = self.valves.ROUTELLM_WEAK_BASE_URL
            logging.info(f"Setting WEAK_MODEL_BASE_URL to: {os.environ['WEAK_MODEL_BASE_URL']}")

    def pipelines(self) -> List[dict]:
        return [{"id": f"routellm.{self.valves.ROUTELLM_ROUTER}", "name": f"RouteLLM/{self.valves.ROUTELLM_ROUTER}"}]

    async def on_startup(self):
        logging.info(f"on_startup:{__name__}")

    async def on_shutdown(self):
        logging.info(f"on_shutdown:{__name__}")

    async def on_valves_updated(self):
        logging.info(f"on_valves_updated:{__name__}")
        self._set_environment_variables()
        self._initialize_controller()

    def _initialize_controller(self):
        try:
            strong_model = self.valves.ROUTELLM_STRONG_MODEL
            weak_model = self.valves.ROUTELLM_WEAK_MODEL

            # Adjust model names if base URLs are provided
            if self.valves.ROUTELLM_STRONG_BASE_URL:
                strong_model = f"openai/{strong_model}"
            if self.valves.ROUTELLM_WEAK_BASE_URL:
                weak_model = f"openai/{weak_model}"
            
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
            response = self.controller.chat.completions.create(
                model=f"router-{self.valves.ROUTELLM_ROUTER}-{self.valves.ROUTELLM_THRESHOLD}",
                messages=messages,
                max_tokens=body.get("max_tokens", 4096),
                temperature=body.get("temperature", 0.8),
                stream=body.get("stream", False),
            )
            
            if body.get("stream", False):
                return (chunk for chunk in response)
            else:
                return response
        except Exception as e:
            logging.error(f"Error in pipe: {e}")
            return f"Error: {e}"
