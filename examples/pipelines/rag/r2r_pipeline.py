"""
title: R2R Pipeline
author: Nolan Tremelling
date: 2025-03-21
version: 1.0
license: MIT
description: A pipeline for retrieving relevant information from a knowledge base using R2R.
requirements: r2r
"""

from typing import List, Union, Generator, Iterator
from schemas import OpenAIChatMessage
import os
import asyncio


class Pipeline:
    def __init__(self):
        self.r2r_client = None

    async def on_startup(self):
        from r2r import R2RClient

        # Connect to either SciPhi cloud or your self hosted R2R server
        self.r2r_client = R2RClient(os.getenv("R2R_SERVER_URL", "https://api.sciphi.ai"))
        self.r2r_client.set_api_key(os.getenv("R2R_API_KEY", ""))

        pass

    async def on_shutdown(self):
        # This function is called when the server is stopped.
        self.r2r_client = None

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:

        print(messages)
        print(user_message)

        response = self.r2r_client.retrieval.rag(
            query=user_message,
        )

        return response.results.completion
