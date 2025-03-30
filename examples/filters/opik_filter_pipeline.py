"""
title: Opik Filter Pipeline
author: open-webui
date: 2025-03-12
version: 1.0
license: MIT
description: A filter pipeline that uses Opik for LLM observability.
requirements: opik
"""

from typing import List, Optional
import os
import uuid
import json

from pydantic import BaseModel
from opik import Opik


def get_last_assistant_message_obj(messages: List[dict]) -> dict:
    for message in reversed(messages):
        if message["role"] == "assistant":
            return message
    return {}


class Pipeline:
    class Valves(BaseModel):
        pipelines: List[str] = []
        priority: int = 0
        api_key: Optional[str] = None
        workspace: str
        project_name: str
        host: str
        debug: bool = False

    def __init__(self):
        self.type = "filter"
        self.name = "Opik Filter"

        self.valves = self.Valves(
            **{
                "pipelines": ["*"],
                "api_key": os.getenv("OPIK_API_KEY", "set_me_for_opik_cloud"),
                "workspace": os.getenv("OPIK_WORKSPACE", "default"),
                "project_name": os.getenv("OPIK_PROJECT_NAME", "default"),
                "host": os.getenv(
                    "OPIK_URL_OVERRIDE", "https://www.comet.com/opik/api"
                ),
                "debug": os.getenv("DEBUG_MODE", "false").lower() == "true",
            }
        )

        self.opik = None
        # Keep track of the trace and the last-created span for each chat_id
        self.chat_traces = {}
        self.chat_spans = {}

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
        self.set_opik()

    async def on_shutdown(self):
        self.log(f"on_shutdown triggered for {__name__}")
        if self.opik:
            self.opik.end()

    async def on_valves_updated(self):
        self.log("Valves updated, resetting Opik client.")
        if self.opik:
            self.opik.end()
        self.set_opik()

    def set_opik(self):
        try:
            self.opik = Opik(
                project_name=self.valves.project_name,
                workspace=self.valves.workspace,
                host=self.valves.host,
                api_key=self.valves.api_key,
            )
            self.opik.auth_check()
            self.log("Opik client initialized successfully.")
        except Exception as e:
            print(
                f"Opik error: {e} Please re-enter your Opik credentials in the pipeline settings."
            )

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        """
        Inlet handles the incoming request (usually a user message).
        - If no trace exists yet for this chat_id, we create a new trace.
        - If a trace does exist, we simply create a new span for the new user message.
        """
        if self.valves.debug:
            print(f"[DEBUG] Received request: {json.dumps(body, indent=2)}")

        self.log(f"Inlet function called with body: {body} and user: {user}")

        metadata = body.get("metadata", {})
        task = metadata.get("task", "")

        # Skip logging tasks for now
        if task:
            self.log(f"Skipping {task} task.")
            return body

        if "chat_id" not in metadata:
            chat_id = str(uuid.uuid4())  # Regular chat messages
            self.log(f"Assigned normal chat_id: {chat_id}")

            metadata["chat_id"] = chat_id
            body["metadata"] = metadata
        else:
            chat_id = metadata["chat_id"]

        required_keys = ["model", "messages"]
        missing_keys = [key for key in required_keys if key not in body]
        if missing_keys:
            error_message = (
                f"Error: Missing keys in the request body: {', '.join(missing_keys)}"
            )
            self.log(error_message)
            raise ValueError(error_message)

        user_email = user.get("email") if user else None

        assert chat_id not in self.chat_traces, (
            f"There shouldn't be a trace already exists for chat_id {chat_id}"
        )

        # Create a new trace and span
        self.log(f"Creating new chat trace for chat_id: {chat_id}")

        # Body copy for traces and span
        trace_body = body.copy()
        span_body = body.copy()

        # Extract metadata from body
        metadata = trace_body.pop("metadata", {})
        metadata.update({"chat_id": chat_id, "user_id": user_email})

        # We don't need the model at the trace level
        trace_body.pop("model", None)

        trace_payload = {
            "name": f"{__name__}",
            "input": trace_body,
            "metadata": metadata,
            "thread_id": chat_id,
        }

        if self.valves.debug:
            print(f"[DEBUG] Opik trace request: {json.dumps(trace_payload, indent=2)}")

        trace = self.opik.trace(**trace_payload)

        span_metadata = metadata.copy()
        span_metadata.update({"interface": "open-webui"})

        # Extract the model from body
        span_body.pop("model", None)
        # We don't need the metadata in the input for the span
        span_body.pop("metadata", None)

        # Extract the model and provider from metadata
        model = span_metadata.get("model", {}).get("id", None)
        provider = span_metadata.get("model", {}).get("owned_by", None)

        span_payload = {
            "name": chat_id,
            "model": model,
            "provider": provider,
            "input": span_body,
            "metadata": span_metadata,
            "type": "llm",
        }

        if self.valves.debug:
            print(f"[DEBUG] Opik span request: {json.dumps(span_payload, indent=2)}")

        span = trace.span(**span_payload)

        self.chat_traces[chat_id] = trace
        self.chat_spans[chat_id] = span
        self.log(f"Trace and span objects successfully created for chat_id: {chat_id}")

        return body

    async def outlet(self, body: dict, user: Optional[dict] = None) -> dict:
        """
        Outlet handles the response body (usually the assistant message).
        It will finalize/end the span created for the user request.
        """
        self.log(f"Outlet function called with body: {body}")

        chat_id = body.get("chat_id")

        # If no trace or span exist, attempt to register again
        if chat_id not in self.chat_traces or chat_id not in self.chat_spans:
            self.log(
                f"[WARNING] No matching chat trace found for chat_id: {chat_id}, chat won't be logged."
            )
            return body

        trace = self.chat_traces[chat_id]
        span = self.chat_spans[chat_id]

        # Body copy for traces and span
        trace_body = body.copy()
        span_body = body.copy()

        # Get the last assistant message from the conversation
        assistant_message_obj = get_last_assistant_message_obj(body["messages"])

        # Extract usage if available
        usage = None
        self.log(f"Assistant message obj: {assistant_message_obj}")
        if assistant_message_obj:
            message_usage = assistant_message_obj.get("usage", {})
            if isinstance(message_usage, dict):
                input_tokens = message_usage.get(
                    "prompt_eval_count"
                ) or message_usage.get("prompt_tokens")
                output_tokens = message_usage.get("eval_count") or message_usage.get(
                    "completion_tokens"
                )
                if input_tokens is not None and output_tokens is not None:
                    usage = {
                        "prompt_tokens": input_tokens,
                        "completion_tokens": output_tokens,
                        "total_tokens": input_tokens + output_tokens,
                    }
                    self.log(f"Usage data extracted: {usage}")

        # Chat_id is already logged as trace thread
        span_body.pop("chat_id", None)

        # End the span with the final assistant message and updated conversation
        span_payload = {
            "output": span_body,  # include the entire conversation
            "usage": usage,
        }

        if self.valves.debug:
            print(
                f"[DEBUG] Opik span end request: {json.dumps(span_payload, indent=2)}"
            )

        span.end(**span_payload)
        self.log(f"span ended for chat_id: {chat_id}")

        # Chat_id is already logged as trace thread
        span_body.pop("chat_id", None)

        # Optionally update the trace with the final assistant output
        trace.end(output=trace_body)

        # Force the creation of a new trace and span for the next chat even if they are part of the same thread
        del self.chat_traces[chat_id]
        del self.chat_spans[chat_id]

        return body
