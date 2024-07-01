"""
title: MLX Manifold Pipeline
author: justinh-rahb
date: 2024-05-28
version: 2.0
license: MIT
description: A pipeline for generating text using Apple MLX Framework with dynamic model loading.
requirements: requests, mlx-lm, huggingface-hub, psutil
environment_variables: MLX_HOST, MLX_PORT, MLX_SUBPROCESS
"""

import argparse
from typing import List, Union, Generator, Iterator
from schemas import OpenAIChatMessage
from pydantic import BaseModel
import requests
import os
import subprocess
import logging
from huggingface_hub import login
import time
import psutil
import json

class Pipeline:
    class Valves(BaseModel):
        MLX_STOP: str = "<|start_header_id|>,<|end_header_id|>,<|eot_id|>"
        HUGGINGFACE_TOKEN: str = ""
        MLX_MODEL_PATTERN: str = "meta-llama"
        MLX_DEFAULT_MODEL: str = "meta-llama/Meta-Llama-3-8B-Instruct"
        MLX_CHAT_TEMPLATE: str = ""
        MLX_USE_DEFAULT_CHAT_TEMPLATE: bool = False

    def __init__(self):
        self.type = "manifold"
        self.id = "mlx"
        self.name = "MLX/"

        self.valves = self.Valves()
        self.update_valves()

        self.host = os.getenv("MLX_HOST", "localhost")
        self.port = os.getenv("MLX_PORT", "8080")
        self.subprocess = os.getenv("MLX_SUBPROCESS", "true").lower() == "true"

        self.models = self.get_mlx_models()
        self.current_model = None
        self.server_process = None

        if self.subprocess:
            self.start_mlx_server(self.valves.MLX_DEFAULT_MODEL)

    def update_valves(self):
        if self.valves.HUGGINGFACE_TOKEN:
            login(self.valves.HUGGINGFACE_TOKEN)
        self.stop_sequence = self.valves.MLX_STOP.split(",")

    def get_mlx_models(self):
        try:
            cmd = [
                'mlx_lm.manage',
                '--scan',
                '--pattern', self.valves.MLX_MODEL_PATTERN,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            lines = result.stdout.strip().split('\n')
            
            # Skip header lines and the line with dashes
            content_lines = [line for line in lines if line and not line.startswith('-')]
            
            models = []
            for line in content_lines[2:]:  # Skip the first two lines (header)
                parts = line.split()
                if len(parts) >= 2:
                    repo_id = parts[0]
                    models.append({
                        "id": f"{repo_id.split('/')[-1].lower()}",
                        "name": repo_id
                    })
            if not models:
                # Add default model if no models are found
                models.append({
                    "id": f"mlx.{self.valves.MLX_DEFAULT_MODEL.split('/')[-1].lower()}",
                    "name": self.valves.MLX_DEFAULT_MODEL
                })
            return models
        except Exception as e:
            logging.error(f"Error fetching MLX models: {e}")
            # Return default model on error
            return [{
                "id": f"mlx.{self.valves.MLX_DEFAULT_MODEL.split('/')[-1].lower()}",
                "name": self.valves.MLX_DEFAULT_MODEL
            }]

    def pipelines(self) -> List[dict]:
        return self.models

    def start_mlx_server(self, model_name):
        model_id = f"mlx.{model_name.split('/')[-1].lower()}"
        if self.current_model == model_id and self.server_process and self.server_process.poll() is None:
            logging.info(f"MLX server already running with model {model_name}")
            return

        self.stop_mlx_server()

        if not os.getenv("MLX_PORT"):
            self.port = self.find_free_port()

        command = [
            "mlx_lm.server",
            "--model", model_name,
            "--port", str(self.port),
        ]

        if self.valves.MLX_CHAT_TEMPLATE:
            command.extend(["--chat-template", self.valves.MLX_CHAT_TEMPLATE])
        elif self.valves.MLX_USE_DEFAULT_CHAT_TEMPLATE:
            command.append("--use-default-chat-template")

        logging.info(f"Starting MLX server with command: {' '.join(command)}")
        self.server_process = subprocess.Popen(command)
        self.current_model = model_id
        logging.info(f"Started MLX server for model {model_name} on port {self.port}")
        time.sleep(5)  # Give the server some time to start up

    def stop_mlx_server(self):
        if self.server_process:
            try:
                process = psutil.Process(self.server_process.pid)
                for proc in process.children(recursive=True):
                    proc.terminate()
                process.terminate()
                process.wait(timeout=10)  # Wait for the process to terminate
            except psutil.NoSuchProcess:
                pass  # Process already terminated
            except psutil.TimeoutExpired:
                logging.warning("Timeout while terminating MLX server process")
            finally:
                self.server_process = None
                self.current_model = None
                logging.info(f"Stopped MLX server on port {self.port}")

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
        if self.subprocess:
            self.stop_mlx_server()

    async def on_valves_updated(self):
        self.update_valves()
        self.models = self.get_mlx_models()
        if self.subprocess:
            self.start_mlx_server(self.valves.MLX_DEFAULT_MODEL)

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        logging.info(f"pipe:{__name__}")

        if model_id != self.current_model:
            model_name = next((model['name'] for model in self.models if model['id'] == model_id), self.valves.MLX_DEFAULT_MODEL)
            self.start_mlx_server(model_name)

        url = f"http://{self.host}:{self.port}/v1/chat/completions"
        headers = {"Content-Type": "application/json"}

        max_tokens = body.get("max_tokens", 4096)
        temperature = body.get("temperature", 0.8)
        repeat_penalty = body.get("repeat_penalty", 1.0)

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