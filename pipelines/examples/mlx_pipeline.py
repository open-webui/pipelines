"""
title: MLX Pipeline
author: justinh-rahb
date: 2024-05-27
version: 1.1
license: MIT
description: A pipeline for generating text using Apple MLX Framework.
dependencies: requests, mlx-lm, huggingface-hub
environment_variables: MLX_HOST, MLX_PORT, MLX_MODEL, MLX_STOP, MLX_SUBPROCESS, HUGGINGFACE_TOKEN
"""

from typing import List, Union, Generator, Iterator
from schemas import OpenAIChatMessage
import requests
import os
import subprocess
import logging
from huggingface_hub import login


class Pipeline:
    def __init__(self):
        # Optionally, you can set the id and name of the pipeline.
        # Assign a unique identifier to the pipeline.
        # The identifier must be unique across all pipelines.
        # The identifier must be an alphanumeric string that can include underscores or hyphens. It cannot contain spaces, special characters, slashes, or backslashes.
        self.id = "mlx_pipeline"
        self.name = "MLX Pipeline"
        self.host = os.getenv("MLX_HOST", "localhost")
        self.port = os.getenv("MLX_PORT", "8080")
        self.model = os.getenv("MLX_MODEL", "mistralai/Mistral-7B-Instruct-v0.2")
        self.stop_sequence = os.getenv("MLX_STOP", "[INST]").split(
            ","
        )  # Default stop sequence is [INST]
        self.subprocess = os.getenv("MLX_SUBPROCESS", "true").lower() == "true"
        self.huggingface_token = os.getenv("HUGGINGFACE_TOKEN", None)

        if self.huggingface_token:
            login(self.huggingface_token)

        if self.subprocess:
            self.start_mlx_server()

    def start_mlx_server(self):
        if not os.getenv("MLX_PORT"):
            self.port = self.find_free_port()
            command = f"mlx_lm.server --model {self.model} --port {self.port}"
            self.server_process = subprocess.Popen(command, shell=True)
            logging.info(f"Started MLX server on port {self.port}")

    def find_free_port(self):
        import socket

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("", 0))
        port = s.getsockname()[1]
        s.close()
        return port

    async def on_startup(self):
        logging.info(f"on_startup:{__name__}")

    async def on_shutdown(self):
        if self.subprocess and hasattr(self, "server_process"):
            self.server_process.terminate()
            logging.info(f"Terminated MLX server on port {self.port}")

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        logging.info(f"pipe:{__name__}")

        url = f"http://{self.host}:{self.port}/v1/chat/completions"
        headers = {"Content-Type": "application/json"}

        # Extract and validate parameters from the request body
        max_tokens = body.get("max_tokens", 4096)
        if not isinstance(max_tokens, int) or max_tokens < 0:
            max_tokens = 4096  # Default to 4096 if invalid

        temperature = body.get("temperature", 0.8)
        if not isinstance(temperature, (int, float)) or temperature < 0:
            temperature = 0.8  # Default to 0.8 if invalid

        repeat_penalty = body.get("repeat_penalty", 1.0)
        if not isinstance(repeat_penalty, (int, float)) or repeat_penalty < 0:
            repeat_penalty = 1.0  # Default to 1.0 if invalid

        payload = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "repetition_penalty": repeat_penalty,
            "stop": self.stop_sequence,
            "stream": body.get("stream", False),
        }

        try:
            r = requests.post(
                url, headers=headers, json=payload, stream=body.get("stream", False)
            )
            r.raise_for_status()

            if body.get("stream", False):
                return r.iter_lines()
            else:
                return r.json()
        except Exception as e:
            return f"Error: {e}"
