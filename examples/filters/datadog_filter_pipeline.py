"""
title: DataDog Filter Pipeline
author: 0xThresh
date: 2024-06-06
version: 1.0
license: MIT
description: A filter pipeline that sends traces to DataDog.
requirements: ddtrace
environment_variables: DD_LLMOBS_AGENTLESS_ENABLED, DD_LLMOBS_ENABLED, DD_LLMOBS_APP_NAME, DD_API_KEY, DD_SITE 
"""

from typing import List, Optional
import os

from utils.pipelines.main import get_last_user_message, get_last_assistant_message
from pydantic import BaseModel
from ddtrace.llmobs import LLMObs


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

        # Valves
        dd_api_key: str
        dd_site: str
        ml_app: str

    def __init__(self):
        # Pipeline filters are only compatible with Open WebUI
        # You can think of filter pipeline as a middleware that can be used to edit the form data before it is sent to the OpenAI API.
        self.type = "filter"

        # Optionally, you can set the id and name of the pipeline.
        # Best practice is to not specify the id so that it can be automatically inferred from the filename, so that users can install multiple versions of the same pipeline.
        # The identifier must be unique across all pipelines.
        # The identifier must be an alphanumeric string that can include underscores or hyphens. It cannot contain spaces, special characters, slashes, or backslashes.
        # self.id = "datadog_filter_pipeline"
        self.name = "DataDog Filter"

        # Initialize
        self.valves = self.Valves(
            **{
                "pipelines": ["*"],  # Connect to all pipelines
                "dd_api_key": os.getenv("DD_API_KEY"),
                "dd_site": os.getenv("DD_SITE", "datadoghq.com"),
                "ml_app": os.getenv("ML_APP", "pipelines-test"),
            }
        )

        # DataDog LLMOBS docs: https://docs.datadoghq.com/tracing/llm_observability/sdk/
        self.LLMObs = LLMObs()
        self.llm_span = None
        self.chat_generations = {}
        pass

    async def on_startup(self):
        # This function is called when the server is started.
        print(f"on_startup:{__name__}")
        self.set_dd()
        pass

    async def on_shutdown(self):
        # This function is called when the server is stopped.
        print(f"on_shutdown:{__name__}")
        self.LLMObs.flush()
        pass

    async def on_valves_updated(self):
        # This function is called when the valves are updated.
        self.set_dd()
        pass

    def set_dd(self):
        self.LLMObs.enable(
            ml_app=self.valves.ml_app,
            api_key=self.valves.dd_api_key,
            site=self.valves.dd_site,
            agentless_enabled=True,
            integrations_enabled=True,
        )

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        print(f"inlet:{__name__}")

        self.llm_span = self.LLMObs.llm(
            model_name=body["model"],
            name=f"filter:{__name__}",
            model_provider="open-webui",
            session_id=body["chat_id"],
            ml_app=self.valves.ml_app
        )

        self.LLMObs.annotate(
            span = self.llm_span,
            input_data = get_last_user_message(body["messages"]),
        )

        return body


    async def outlet(self, body: dict, user: Optional[dict] = None) -> dict:
        print(f"outlet:{__name__}")

        self.LLMObs.annotate(
            span = self.llm_span,
            output_data = get_last_assistant_message(body["messages"]),
        )

        self.llm_span.finish()
        self.LLMObs.flush()

        return body
