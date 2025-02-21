"""
title: Langfuse Filter Pipeline
author: open-webui
date: 2024-09-27
version: 1.6
license: MIT
description: A filter pipeline that uses Langfuse.
requirements: langfuse
"""

from typing import List, Optional
import os
import uuid
import json

from utils.pipelines.main import get_last_assistant_message
from pydantic import BaseModel
from langfuse import Langfuse
from langfuse.api.resources.commons.errors.unauthorized_error import UnauthorizedError


def get_last_assistant_message_obj(messages: List[dict]) -> dict:
    """Retrieve the last assistant message from the message list."""
    for message in reversed(messages):
        if message["role"] == "assistant":
            return message
    return {}


class Pipeline:
    class Valves(BaseModel):
        pipelines: List[str] = []
        priority: int = 0
        secret_key: str
        public_key: str
        host: str
        debug: bool = False

    def __init__(self):
        self.type = "filter"
        self.name = "Langfuse Filter"

        self.valves = self.Valves(
            **{
                "pipelines": ["*"],
                "secret_key": os.getenv("LANGFUSE_SECRET_KEY", "your-secret-key-here"),
                "public_key": os.getenv("LANGFUSE_PUBLIC_KEY", "your-public-key-here"),
                "host": os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
                "debug": os.getenv("DEBUG_MODE", "false").lower() == "true",
            }
        )

        self.langfuse = None
        self.chat_traces = {}
        self.suppressed_logs = set()

    def log(self, message: str, suppress_repeats: bool = False):
        if self.valves.debug:
            if suppress_repeats:
                if message in self.suppressed_logs:
                    return
                self.suppressed_logs.add(message)
            print(f"[DEBUG] {message}")

    async def on_startup(self):
        self.log(f"on_startup triggered for {__name__}")
        self.set_langfuse()

    async def on_shutdown(self):
        self.log(f"on_shutdown triggered for {__name__}")
        if self.langfuse:
            self.langfuse.flush()

    async def on_valves_updated(self):
        self.log("Valves updated, resetting Langfuse client.")
        self.set_langfuse()

    def set_langfuse(self):
        try:
            self.langfuse = Langfuse(
                secret_key=self.valves.secret_key,
                public_key=self.valves.public_key,
                host=self.valves.host,
                debug=self.valves.debug,
            )
            self.langfuse.auth_check()
            self.log("Langfuse client initialized successfully.")
        except UnauthorizedError:
            print(
                "Langfuse credentials incorrect. Please re-enter your Langfuse credentials in the pipeline settings."
            )
        except Exception as e:
            print(
                f"Langfuse error: {e} Please re-enter your Langfuse credentials in the pipeline settings."
            )

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        if self.valves.debug:
            print(f"[DEBUG] Received request: {json.dumps(body, indent=2)}")

        self.log(f"Inlet function called with body: {body} and user: {user}")

        metadata = body.get("metadata", {})
        chat_id = metadata.get("chat_id", str(uuid.uuid4()))
        metadata["chat_id"] = chat_id
        body["metadata"] = metadata

        required_keys = ["model", "messages"]
        missing_keys = [key for key in required_keys if key not in body]
        if missing_keys:
            error_message = f"Error: Missing keys in the request body: {', '.join(missing_keys)}"
            self.log(error_message)
            raise ValueError(error_message)

        user_email = user.get("email") if user else None
        task_name = metadata.get("task", "user_response")  # Default to user_response if task is missing

        # **Extract system message from metadata and prepend**
        system_message = ""
        if "model" in metadata and "params" in metadata["model"]:
            system_message = metadata["model"]["params"].get("system", "")

        for message in body["messages"]:
            if message["role"] == "system":
                message["content"] = system_message + "\n\n" + message["content"]
                break
        else:
            # If no system message was found, add one
            if system_message:
                body["messages"].insert(0, {"role": "system", "content": system_message})

        # Ensure unique tracking per task
        if chat_id not in self.chat_traces:
            self.log(f"Creating new trace for chat_id: {chat_id}")

            trace_payload = {
                "name": f"chat:{chat_id}",
                "input": body,
                "user_id": user_email,
                "metadata": metadata,  # Preserve all metadata
                "session_id": chat_id,
            }

            if self.valves.debug:
                print(f"[DEBUG] Langfuse trace request: {json.dumps(trace_payload, indent=2)}")

            trace = self.langfuse.trace(**trace_payload)
            self.chat_traces[chat_id] = trace
        else:
            trace = self.chat_traces[chat_id]
            self.log(f"Reusing existing trace for chat_id: {chat_id}")

        # Ensure all metadata fields are passed through
        metadata["type"] = task_name
        metadata["interface"] = "open-webui"

        generation_payload = {
            "name": f"{task_name}:{str(uuid.uuid4())}",
            "model": body["model"],
            "input": body["messages"],
            "metadata": metadata,  # Preserve all metadata
        }

        if self.valves.debug:
            print(f"[DEBUG] Langfuse generation request: {json.dumps(generation_payload, indent=2)}")

        trace.generation(**generation_payload)

        return body

    async def outlet(self, body: dict, user: Optional[dict] = None) -> dict:
        self.log(f"Outlet function called with body: {body}")

        chat_id = body.get("chat_id")
        metadata = body.get("metadata", {})
        task_name = metadata.get("task", "llm_response")  # Default to llm_response if missing

        if chat_id not in self.chat_traces:
            self.log(f"[WARNING] No matching trace found for chat_id: {chat_id}, attempting to re-register.")
            return await self.inlet(body, user)

        trace = self.chat_traces[chat_id]

        assistant_message = get_last_assistant_message(body["messages"])

        usage = None
        assistant_message_obj = get_last_assistant_message_obj(body["messages"])
        if assistant_message_obj:
            info = assistant_message_obj.get("info", {})
            if isinstance(info, dict):
                input_tokens = info.get("prompt_eval_count") or info.get("prompt_tokens")
                output_tokens = info.get("eval_count") or info.get("completion_tokens")
                if input_tokens is not None and output_tokens is not None:
                    usage = {
                        "input": input_tokens,
                        "output": output_tokens,
                        "unit": "TOKENS",
                    }
                    self.log(f"Usage data extracted: {usage}")

        trace.update(output=assistant_message)

        metadata["type"] = task_name
        metadata["interface"] = "open-webui"

        generation_payload = {
            "name": f"{task_name}:{str(uuid.uuid4())}",
            "input": body["messages"],
            "metadata": metadata,  # Preserve all metadata
            "usage": usage,
        }

        if self.valves.debug:
            print(f"[DEBUG] Langfuse generation end request: {json.dumps(generation_payload, indent=2)}")

        trace.generation().end(**generation_payload)
        self.log(f"Generation ended for chat_id: {chat_id}")

        return body
