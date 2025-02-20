"""
title: Langfuse Filter Pipeline
author: open-webui
date: 2025-02-20
version: 1.5
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
        # Keep track of the trace and the last-created generation for each chat_id
        self.chat_traces = {}
        self.chat_generations = {}
        self.suppressed_logs = set()

    def log(self, message: str, suppress_repeats: bool = False):
        """Logs messages to the terminal if debugging is enabled."""
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
        """
        Inlet handles the incoming request (usually a user message).
        - If no trace exists yet for this chat_id, we create a new trace.
        - If a trace does exist, we simply create a new generation for the new user message.
        """
        if self.valves.debug:
            print(f"[DEBUG] Received request: {json.dumps(body, indent=2)}")

        self.log(f"Inlet function called with body: {body} and user: {user}")

        metadata = body.get("metadata", {})

        # ---------------------------------------------------------
        # Prepend the system prompt from metadata to the system message:
        model_info = metadata.get("model", {})
        params_info = model_info.get("params", {})
        system_prompt = params_info.get("system", "")

        if system_prompt:
            for msg in body["messages"]:
                if msg.get("role") == "system":
                    # Only prepend if it hasn't already been prepended:
                    if not msg["content"].startswith("System Prompt:"):
                        msg["content"] = f"System Prompt:\n{system_prompt}\n\n{msg['content']}"
                    break
        # ---------------------------------------------------------

        # Fix SYSTEM MESSAGE prefix issue: Only apply for "task_generation"
        if "chat_id" not in metadata:
            if "task_generation" in metadata.get("type", "").lower():
                chat_id = f"SYSTEM MESSAGE {uuid.uuid4()}"
                self.log(f"Task Generation detected, assigned SYSTEM MESSAGE ID: {chat_id}")
            else:
                chat_id = str(uuid.uuid4())  # Regular chat messages
                self.log(f"Assigned normal chat_id: {chat_id}")

            metadata["chat_id"] = chat_id
            body["metadata"] = metadata
        else:
            chat_id = metadata["chat_id"]

        required_keys = ["model", "messages"]
        missing_keys = [key for key in required_keys if key not in body]
        if missing_keys:
            error_message = f"Error: Missing keys in the request body: {', '.join(missing_keys)}"
            self.log(error_message)
            raise ValueError(error_message)

        user_email = user.get("email") if user else None

        # Check if we already have a trace for this chat
        if chat_id not in self.chat_traces:
            # Create a new trace and generation
            self.log(f"Creating new chat trace for chat_id: {chat_id}")

            trace_payload = {
                "name": f"filter:{__name__}",
                "input": body,
                "user_id": user_email,
                "metadata": {"chat_id": chat_id},
                "session_id": chat_id,
            }

            if self.valves.debug:
                print(f"[DEBUG] Langfuse trace request: {json.dumps(trace_payload, indent=2)}")

            trace = self.langfuse.trace(**trace_payload)

            generation_payload = {
                "name": chat_id,
                "model": body["model"],
                "input": body["messages"],
                "metadata": {"interface": "open-webui"},
            }

            if self.valves.debug:
                print(f"[DEBUG] Langfuse generation request: {json.dumps(generation_payload, indent=2)}")

            generation = trace.generation(**generation_payload)

            self.chat_traces[chat_id] = trace
            self.chat_generations[chat_id] = generation
            self.log(f"Trace and generation objects successfully created for chat_id: {chat_id}")

        else:
            # Re-use existing trace but create a new generation for each new message
            self.log(f"Re-using existing chat trace for chat_id: {chat_id}")
            trace = self.chat_traces[chat_id]

            new_generation_payload = {
                "name": f"{chat_id}:{str(uuid.uuid4())}",
                "model": body["model"],
                "input": body["messages"],
                "metadata": {"interface": "open-webui"},
            }
            if self.valves.debug:
                print(f"[DEBUG] Langfuse new_generation request: {json.dumps(new_generation_payload, indent=2)}")

            new_generation = trace.generation(**new_generation_payload)
            self.chat_generations[chat_id] = new_generation

        return body

    async def outlet(self, body: dict, user: Optional[dict] = None) -> dict:
        """
        Outlet handles the response body (usually the assistant message).
        It will finalize/end the generation created for the user request.
        """
        self.log(f"Outlet function called with body: {body}")

        chat_id = body.get("chat_id")

        # If no trace or generation exist, attempt to register again
        if chat_id not in self.chat_traces or chat_id not in self.chat_generations:
            self.log(f"[WARNING] No matching chat trace found for chat_id: {chat_id}, attempting to re-register.")
            return await self.inlet(body, user)

        trace = self.chat_traces[chat_id]
        generation = self.chat_generations[chat_id]

        # Get the last assistant message from the conversation
        assistant_message = get_last_assistant_message(body["messages"])
        assistant_message_obj = get_last_assistant_message_obj(body["messages"])

        # ---------------------------------------------------------
        # If the outlet contains a sources array, append it after the "System Prompt:"
        # section in the system message:
        if assistant_message_obj and "sources" in assistant_message_obj and assistant_message_obj["sources"]:
            for msg in body["messages"]:
                if msg.get("role") == "system":
                    if msg["content"].startswith("System Prompt:"):
                        # Format the sources nicely
                        sources_str = "\n\n".join(
                            json.dumps(src, indent=2) for src in assistant_message_obj["sources"]
                        )
                        msg["content"] += f"\n\nSources:\n{sources_str}"
                    break
        # ---------------------------------------------------------

        # Extract usage if available
        usage = None
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

        # Optionally update the trace with the final assistant output
        trace.update(output=assistant_message)

        # End the generation with the final assistant message and updated conversation
        generation_payload = {
            "input": body["messages"],  # include the entire conversation
            "metadata": {"interface": "open-webui"},
            "usage": usage,
        }

        if self.valves.debug:
            print(f"[DEBUG] Langfuse generation end request: {json.dumps(generation_payload, indent=2)}")

        generation.end(**generation_payload)
        self.log(f"Generation ended for chat_id: {chat_id}")

        return body
