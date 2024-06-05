"""
title: Llama C++ Pipeline
author: open-webui
date: 2024-05-30
version: 1.0
license: MIT
description: A pipeline for generating responses using the Llama C++ library.
requirements: llama-cpp-python
"""

from typing import List, Union, Generator, Iterator
from schemas import OpenAIChatMessage


class Pipeline:
    def __init__(self):
        # Optionally, you can set the id and name of the pipeline.
        # Best practice is to not specify the id so that it can be automatically inferred from the filename, so that users can install multiple versions of the same pipeline.
        # The identifier must be unique across all pipelines.
        # The identifier must be an alphanumeric string that can include underscores or hyphens. It cannot contain spaces, special characters, slashes, or backslashes.
        # self.id = "llama_cpp_pipeline"

        self.name = "Llama C++ Pipeline"
        self.llm = None
        pass

    async def on_startup(self):
        # This function is called when the server is started.
        print(f"on_startup:{__name__}")
        from llama_cpp import Llama

        self.llm = Llama(
            model_path="./models/llama3.gguf",
            # n_gpu_layers=-1, # Uncomment to use GPU acceleration
            # seed=1337, # Uncomment to set a specific seed
            # n_ctx=2048, # Uncomment to increase the context window
        )

        pass

    async def on_shutdown(self):
        # This function is called when the server is stopped.
        print(f"on_shutdown:{__name__}")
        pass

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        # This is where you can add your custom pipelines like RAG.
        print(f"pipe:{__name__}")

        print(messages)
        print(user_message)
        print(body)

        response = self.llm.create_chat_completion_openai_v1(
            messages=messages,
            stream=body["stream"],
        )

        return response
