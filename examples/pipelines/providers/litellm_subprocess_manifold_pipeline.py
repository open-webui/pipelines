"""
title: LiteLLM Subprocess Manifold Pipeline
author: open-webui
date: 2024-05-30
version: 1.0
license: MIT
description: A manifold pipeline that uses LiteLLM as a subprocess.
requirements: yaml, litellm[proxy]
"""

from typing import List, Union, Generator, Iterator
from schemas import OpenAIChatMessage
from pydantic import BaseModel
import requests


import os
import asyncio
import subprocess
import yaml


class Pipeline:
    class Valves(BaseModel):
        LITELLM_CONFIG_DIR: str = "./litellm/config.yaml"
        LITELLM_PROXY_PORT: int = 4001
        LITELLM_PROXY_HOST: str = "127.0.0.1"
        litellm_config: dict = {}

    def __init__(self):
        # You can also set the pipelines that are available in this pipeline.
        # Set manifold to True if you want to use this pipeline as a manifold.
        # Manifold pipelines can have multiple pipelines.
        self.type = "manifold"

        # Optionally, you can set the id and name of the pipeline.
        # Best practice is to not specify the id so that it can be automatically inferred from the filename, so that users can install multiple versions of the same pipeline.
        # The identifier must be unique across all pipelines.
        # The identifier must be an alphanumeric string that can include underscores or hyphens. It cannot contain spaces, special characters, slashes, or backslashes.
        # self.id = "litellm_subprocess_manifold"

        # Optionally, you can set the name of the manifold pipeline.
        self.name = "LiteLLM: "

        # Initialize Valves
        self.valves = self.Valves(**{"LITELLM_CONFIG_DIR": f"./litellm/config.yaml"})
        self.background_process = None
        pass

    async def on_startup(self):
        # This function is called when the server is started.
        print(f"on_startup:{__name__}")

        # Check if the config file exists
        if not os.path.exists(self.valves.LITELLM_CONFIG_DIR):
            with open(self.valves.LITELLM_CONFIG_DIR, "w") as file:
                yaml.dump(
                    {
                        "general_settings": {},
                        "litellm_settings": {},
                        "model_list": [],
                        "router_settings": {},
                    },
                    file,
                )

            print(
                f"Config file not found. Created a default config file at {self.valves.LITELLM_CONFIG_DIR}"
            )

        with open(self.valves.LITELLM_CONFIG_DIR, "r") as file:
            litellm_config = yaml.safe_load(file)

        self.valves.litellm_config = litellm_config

        asyncio.create_task(self.start_litellm_background())
        pass

    async def on_shutdown(self):
        # This function is called when the server is stopped.
        print(f"on_shutdown:{__name__}")
        await self.shutdown_litellm_background()
        pass

    async def on_valves_updated(self):
        # This function is called when the valves are updated.

        print(f"on_valves_updated:{__name__}")

        with open(self.valves.LITELLM_CONFIG_DIR, "r") as file:
            litellm_config = yaml.safe_load(file)

        self.valves.litellm_config = litellm_config

        await self.shutdown_litellm_background()
        await self.start_litellm_background()
        pass

    async def run_background_process(self, command):
        print("run_background_process")

        try:
            # Log the command to be executed
            print(f"Executing command: {command}")

            # Execute the command and create a subprocess
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.background_process = process
            print("Subprocess started successfully.")

            # Capture STDERR for debugging purposes
            stderr_output = await process.stderr.read()
            stderr_text = stderr_output.decode().strip()
            if stderr_text:
                print(f"Subprocess STDERR: {stderr_text}")

            # log.info output line by line
            async for line in process.stdout:
                print(line.decode().strip())

            # Wait for the process to finish
            returncode = await process.wait()
            print(f"Subprocess exited with return code {returncode}")
        except Exception as e:
            print(f"Failed to start subprocess: {e}")
            raise  # Optionally re-raise the exception if you want it to propagate

    async def start_litellm_background(self):
        print("start_litellm_background")
        # Command to run in the background
        command = [
            "litellm",
            "--port",
            str(self.valves.LITELLM_PROXY_PORT),
            "--host",
            self.valves.LITELLM_PROXY_HOST,
            "--telemetry",
            "False",
            "--config",
            self.valves.LITELLM_CONFIG_DIR,
        ]

        await self.run_background_process(command)

    async def shutdown_litellm_background(self):
        print("shutdown_litellm_background")

        if self.background_process:
            self.background_process.terminate()
            await self.background_process.wait()  # Ensure the process has terminated
            print("Subprocess terminated")
            self.background_process = None

    def get_litellm_models(self):
        if self.background_process:
            try:
                r = requests.get(
                    f"http://{self.valves.LITELLM_PROXY_HOST}:{self.valves.LITELLM_PROXY_PORT}/v1/models"
                )
                models = r.json()
                return [
                    {
                        "id": model["id"],
                        "name": model["name"] if "name" in model else model["id"],
                    }
                    for model in models["data"]
                ]
            except Exception as e:
                print(f"Error: {e}")
                return [
                    {
                        "id": "error",
                        "name": "Could not fetch models from LiteLLM, please update the URL in the valves.",
                    },
                ]
        else:
            return []

    # Pipelines are the models that are available in the manifold.
    # It can be a list or a function that returns a list.
    def pipelines(self) -> List[dict]:
        return self.get_litellm_models()

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        if "user" in body:
            print("######################################")
            print(f'# User: {body["user"]["name"]} ({body["user"]["id"]})')
            print(f"# Message: {user_message}")
            print("######################################")

        try:
            r = requests.post(
                url=f"http://{self.valves.LITELLM_PROXY_HOST}:{self.valves.LITELLM_PROXY_PORT}/v1/chat/completions",
                json={**body, "model": model_id, "user": body["user"]["id"]},
                stream=True,
            )

            r.raise_for_status()

            if body["stream"]:
                return r.iter_lines()
            else:
                return r.json()
        except Exception as e:
            return f"Error: {e}"
