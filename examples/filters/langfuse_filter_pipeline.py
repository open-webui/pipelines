"""
title: Langfuse Filter Pipeline
author: open-webui
date: 2025-06-16
version: 1.7.1
license: MIT
description: A filter pipeline that uses Langfuse.
requirements: langfuse<3.0.0
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
        # New valve that controls whether task names are added as tags:
        insert_tags: bool = True
        # New valve that controls whether to use model name instead of model ID for generation
        use_model_name_instead_of_id_for_generation: bool = False
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
                "use_model_name_instead_of_id_for_generation": os.getenv("USE_MODEL_NAME", "false").lower() == "true",
                "debug": os.getenv("DEBUG_MODE", "false").lower() == "true",
            }
        )

        self.langfuse = None
        self.chat_traces = {}
        self.suppressed_logs = set()
        # Dictionary to store model names for each chat
        self.model_names = {}

        # Only these tasks will be treated as LLM "generations":
        self.GENERATION_TASKS = {"llm_response"}

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

    def _build_tags(self, task_name: str) -> list:
        """
        Builds a list of tags based on valve settings, ensuring we always add
        'open-webui' and skip user_response / llm_response from becoming tags themselves.
        """
        tags_list = []
        if self.valves.insert_tags:
            # Always add 'open-webui'
            tags_list.append("open-webui")
            # Add the task_name if it's not one of the excluded defaults
            if task_name not in ["user_response", "llm_response"]:
                tags_list.append(task_name)
        return tags_list

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        if self.valves.debug:
            print(f"[DEBUG] Received request: {json.dumps(body, indent=2)}")

        self.log(f"Inlet function called with body: {body} and user: {user}")

        metadata = body.get("metadata", {})
        chat_id = metadata.get("chat_id", str(uuid.uuid4()))

        # Handle temporary chats
        if chat_id == "local":
            session_id = metadata.get("session_id")
            chat_id = f"temporary-session-{session_id}"

        metadata["chat_id"] = chat_id
        body["metadata"] = metadata

        # Extract and store both model name and ID if available
        model_info = metadata.get("model", {})
        model_id = body.get("model")
        
        # Store model information for this chat
        if chat_id not in self.model_names:
            self.model_names[chat_id] = {"id": model_id}
        else:
            self.model_names[chat_id]["id"] = model_id
            
        if isinstance(model_info, dict) and "name" in model_info:
            self.model_names[chat_id]["name"] = model_info["name"]
            self.log(f"Stored model info - name: '{model_info['name']}', id: '{model_id}' for chat_id: {chat_id}")

        required_keys = ["model", "messages"]
        missing_keys = [key for key in required_keys if key not in body]
        if missing_keys:
            error_message = f"Error: Missing keys in the request body: {', '.join(missing_keys)}"
            self.log(error_message)
            raise ValueError(error_message)

        user_email = user.get("email") if user else None
        # Defaulting to 'user_response' if no task is provided
        task_name = metadata.get("task", "user_response")

        # Build tags
        tags_list = self._build_tags(task_name)

        if chat_id not in self.chat_traces:
            self.log(f"Creating new trace for chat_id: {chat_id}")

            trace_payload = {
                "name": f"chat:{chat_id}",
                "input": body,
                "user_id": user_email,
                "metadata": metadata,
                "session_id": chat_id,
            }

            if tags_list:
                trace_payload["tags"] = tags_list

            if self.valves.debug:
                print(f"[DEBUG] Langfuse trace request: {json.dumps(trace_payload, indent=2)}")

            trace = self.langfuse.trace(**trace_payload)
            self.chat_traces[chat_id] = trace
        else:
            trace = self.chat_traces[chat_id]
            self.log(f"Reusing existing trace for chat_id: {chat_id}")
            if tags_list:
                trace.update(tags=tags_list)

        # Update metadata with type
        metadata["type"] = task_name
        metadata["interface"] = "open-webui"

        # If it's a task that is considered an LLM generation
        if task_name in self.GENERATION_TASKS:
            # Determine which model value to use based on the use_model_name valve
            model_id = self.model_names.get(chat_id, {}).get("id", body["model"])
            model_name = self.model_names.get(chat_id, {}).get("name", "unknown")
            
            # Pick primary model identifier based on valve setting
            model_value = model_name if self.valves.use_model_name_instead_of_id_for_generation else model_id
            
            # Add both values to metadata regardless of valve setting
            metadata["model_id"] = model_id
            metadata["model_name"] = model_name
            
            generation_payload = {
                "name": f"{task_name}:{str(uuid.uuid4())}",
                "model": model_value,
                "input": body["messages"],
                "metadata": metadata,
            }
            if tags_list:
                generation_payload["tags"] = tags_list

            if self.valves.debug:
                print(f"[DEBUG] Langfuse generation request: {json.dumps(generation_payload, indent=2)}")

            trace.generation(**generation_payload)
        else:
            # Otherwise, log it as an event
            event_payload = {
                "name": f"{task_name}:{str(uuid.uuid4())}",
                "metadata": metadata,
                "input": body["messages"],
            }
            if tags_list:
                event_payload["tags"] = tags_list

            if self.valves.debug:
                print(f"[DEBUG] Langfuse event request: {json.dumps(event_payload, indent=2)}")

            trace.event(**event_payload)

        return body

    async def outlet(self, body: dict, user: Optional[dict] = None) -> dict:
        self.log(f"Outlet function called with body: {body}")

        chat_id = body.get("chat_id")

        # Handle temporary chats
        if chat_id == "local":
            session_id = body.get("session_id")
            chat_id = f"temporary-session-{session_id}"

        metadata = body.get("metadata", {})
        # Defaulting to 'llm_response' if no task is provided
        task_name = metadata.get("task", "llm_response")

        # Build tags
        tags_list = self._build_tags(task_name)

        if chat_id not in self.chat_traces:
            self.log(f"[WARNING] No matching trace found for chat_id: {chat_id}, attempting to re-register.")
            # Re-run inlet to register if somehow missing
            return await self.inlet(body, user)

        trace = self.chat_traces[chat_id]

        assistant_message = get_last_assistant_message(body["messages"])
        assistant_message_obj = get_last_assistant_message_obj(body["messages"])

        usage = None
        if assistant_message_obj:
            info = assistant_message_obj.get("usage", {})
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

        # Update the trace output with the last assistant message
        trace.update(output=assistant_message)

        metadata["type"] = task_name
        metadata["interface"] = "open-webui"

        if task_name in self.GENERATION_TASKS:
            # Determine which model value to use based on the use_model_name valve
            model_id = self.model_names.get(chat_id, {}).get("id", body.get("model"))
            model_name = self.model_names.get(chat_id, {}).get("name", "unknown")
            
            # Pick primary model identifier based on valve setting
            model_value = model_name if self.valves.use_model_name_instead_of_id_for_generation else model_id
            
            # Add both values to metadata regardless of valve setting
            metadata["model_id"] = model_id
            metadata["model_name"] = model_name
            
            # If it's an LLM generation
            generation_payload = {
                "name": f"{task_name}:{str(uuid.uuid4())}",
                "model": model_value,   # <-- Use model name or ID based on valve setting
                "input": body["messages"],
                "metadata": metadata,
                "usage": usage,
            }
            if tags_list:
                generation_payload["tags"] = tags_list

            if self.valves.debug:
                print(f"[DEBUG] Langfuse generation end request: {json.dumps(generation_payload, indent=2)}")

            trace.generation().end(**generation_payload)
            self.log(f"Generation ended for chat_id: {chat_id}")
        else:
            # Otherwise log as an event
            event_payload = {
                "name": f"{task_name}:{str(uuid.uuid4())}",
                "metadata": metadata,
                "input": body["messages"],
            }
            if usage:
                # If you want usage on event as well
                event_payload["metadata"]["usage"] = usage

            if tags_list:
                event_payload["tags"] = tags_list

            if self.valves.debug:
                print(f"[DEBUG] Langfuse event end request: {json.dumps(event_payload, indent=2)}")

            trace.event(**event_payload)
            self.log(f"Event logged for chat_id: {chat_id}")

        return body
