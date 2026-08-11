"""
title: Langfuse Filter Pipeline for v4
author: open-webui
date: 2026-08-11
version: 0.1.0
license: MIT
description: A filter pipeline that traces OpenWebUI chats with Langfuse v4.
requirements: langfuse~=4.7
"""

import os
import uuid
from typing import List, Optional

from langfuse import Langfuse, propagate_attributes
from pydantic import BaseModel, Field
from utils.pipelines.main import get_last_assistant_message


def get_last_assistant_message_obj(messages: List[dict]) -> dict:
    """Retrieve the last assistant message from the message list."""
    for message in reversed(messages):
        if message["role"] == "assistant":
            return message
    return {}


class Pipeline:
    class Valves(BaseModel):
        pipelines: List[str] = Field(default_factory=list)
        priority: int = 0
        secret_key: str
        public_key: str
        host: str
        insert_tags: bool = True
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
                "use_model_name_instead_of_id_for_generation": os.getenv(
                    "USE_MODEL_NAME", "false"
                ).lower()
                == "true",
                "debug": os.getenv("DEBUG_MODE", "false").lower() == "true",
            }
        )

        self.langfuse = None
        # A turn root stays open between inlet and outlet so the response generation
        # is its child. Every turn in a chat uses the same deterministic trace ID.
        self.chat_traces = {}
        self.model_names = {}
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
        self._close_active_traces()
        self._flush()

    async def on_valves_updated(self):
        self.log("Valves updated, resetting Langfuse client.")
        self._close_active_traces()
        self._flush()
        self.set_langfuse()

    def set_langfuse(self):
        try:
            self.log(f"Initializing Langfuse with host: {self.valves.host}")
            self.langfuse = Langfuse(
                secret_key=self.valves.secret_key,
                public_key=self.valves.public_key,
                base_url=self.valves.host,
                debug=self.valves.debug,
            )
            self.langfuse.auth_check()
            self.log(
                "Langfuse client initialized and authenticated successfully. "
                f"Connected to host: {self.valves.host}"
            )
        except Exception as error:
            self.log(f"Langfuse initialization or authentication failed: {error}")
            self.langfuse = None

    def _build_tags(self, task_name: str) -> list:
        tags = []
        if self.valves.insert_tags:
            tags.append("open-webui")
            if task_name not in ["user_response", "llm_response"]:
                tags.append(task_name)
        return tags

    @staticmethod
    def _chat_id(data: dict) -> str:
        metadata = data.get("metadata", {})
        chat_id = data.get("chat_id") or metadata.get("chat_id") or str(uuid.uuid4())
        if chat_id == "local":
            session_id = data.get("session_id") or metadata.get("session_id")
            return f"temporary-session-{session_id}"
        return chat_id

    @staticmethod
    def _propagated_metadata(chat_id: str, task_name: str) -> dict:
        # Propagated metadata is intentionally small because v4 trace attributes
        # must fit in OpenTelemetry baggage-sized string values.
        return {
            "chat_id": chat_id,
            "interface": "open-webui",
            "task": task_name,
        }

    def _end_trace(self, chat_id: str):
        trace = self.chat_traces.pop(chat_id, None)
        self.model_names.pop(chat_id, None)
        if trace:
            try:
                trace.end()
                self.log(f"Ended turn root for chat_id: {chat_id}")
            except Exception as error:
                self.log(f"Failed to end turn root for {chat_id}: {error}")

    def _close_active_traces(self):
        for chat_id in list(self.chat_traces):
            self._end_trace(chat_id)

    def _flush(self):
        if not self.langfuse:
            return
        try:
            self.langfuse.flush()
            self.log("Langfuse data flushed")
        except Exception as error:
            self.log(f"Failed to flush Langfuse data: {error}")

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        self.log("Langfuse Filter INLET called")
        if not self.langfuse:
            self.log("[WARNING] Langfuse client not initialized - Skipped")
            return body

        required_keys = ["model", "messages"]
        missing_keys = [key for key in required_keys if key not in body]
        if missing_keys:
            error_message = "Error: Missing keys in the request body: " + ", ".join(
                missing_keys
            )
            self.log(error_message)
            raise ValueError(error_message)

        metadata = body.get("metadata", {})
        chat_id = self._chat_id(body)
        metadata["chat_id"] = chat_id
        body["metadata"] = metadata

        user_email = user.get("email") if user else None
        task_name = metadata.get("task", "user_response")
        tags = self._build_tags(task_name)
        trace_metadata = {
            **metadata,
            "user_id": user_email,
            "session_id": chat_id,
            "interface": "open-webui",
        }

        # If a previous request never reached outlet, close its root before
        # replacing it so a failed request cannot leak an active span forever.
        self._end_trace(chat_id)

        model_info = metadata.get("model", {})
        self.model_names[chat_id] = {"id": body.get("model")}
        if isinstance(model_info, dict) and "name" in model_info:
            self.model_names[chat_id]["name"] = model_info["name"]

        try:
            trace_id = self.langfuse.create_trace_id(seed=chat_id)
            with propagate_attributes(
                trace_name=f"chat:{chat_id}",
                user_id=user_email,
                session_id=chat_id,
                tags=tags or None,
                metadata=self._propagated_metadata(chat_id, task_name),
            ):
                trace = self.langfuse.start_observation(
                    trace_context={"trace_id": trace_id},
                    name=f"chat:{chat_id}",
                    input=body,
                    metadata=trace_metadata,
                )
                self.chat_traces[chat_id] = trace

                user_input = trace.start_observation(
                    as_type="span",
                    name=f"user_input:{uuid.uuid4()}",
                    input=body["messages"],
                    metadata={
                        **trace_metadata,
                        "type": "user_input",
                        "event_id": str(uuid.uuid4()),
                    },
                )
                user_input.end()
            self.log(f"User input logged for chat_id: {chat_id}")
        except Exception as error:
            self.log(f"Failed to create Langfuse observations: {error}")
            self._end_trace(chat_id)

        return body

    async def outlet(self, body: dict, user: Optional[dict] = None) -> dict:
        self.log("Langfuse Filter OUTLET called")
        if not self.langfuse:
            self.log("[WARNING] Langfuse client not initialized - Skipped")
            return body

        chat_id = self._chat_id(body)
        if chat_id not in self.chat_traces:
            self.log(
                f"[WARNING] No matching trace found for chat_id: {chat_id}, "
                "attempting to re-register."
            )
            return await self.inlet(body, user)

        metadata = body.get("metadata", {})
        task_name = metadata.get("task", "llm_response")
        tags = self._build_tags(task_name)
        user_email = user.get("email") if user else None
        assistant_message = get_last_assistant_message(body["messages"])
        assistant_message_obj = get_last_assistant_message_obj(body["messages"])

        usage_details = None
        if assistant_message_obj:
            info = assistant_message_obj.get("usage", {})
            if isinstance(info, dict):
                input_tokens = info.get("prompt_eval_count") or info.get(
                    "prompt_tokens"
                )
                output_tokens = info.get("eval_count") or info.get("completion_tokens")
                if input_tokens is not None and output_tokens is not None:
                    usage_details = {
                        "input": input_tokens,
                        "output": output_tokens,
                    }

        model_id = self.model_names.get(chat_id, {}).get("id", body.get("model"))
        model_name = self.model_names.get(chat_id, {}).get("name", "unknown")
        model_value = (
            model_name
            if self.valves.use_model_name_instead_of_id_for_generation
            else model_id
        )
        complete_metadata = {
            **metadata,
            "user_id": user_email,
            "session_id": chat_id,
            "interface": "open-webui",
            "task": task_name,
            "model_id": model_id,
            "model_name": model_name,
        }

        trace = self.chat_traces[chat_id]
        try:
            trace.update(output=assistant_message, metadata=complete_metadata)
            with propagate_attributes(
                trace_name=f"chat:{chat_id}",
                user_id=user_email,
                session_id=chat_id,
                tags=tags or None,
                metadata=self._propagated_metadata(chat_id, task_name),
            ):
                generation = trace.start_observation(
                    as_type="generation",
                    name=f"llm_response:{uuid.uuid4()}",
                    model=model_value,
                    input=body["messages"],
                    output=assistant_message,
                    metadata={
                        **complete_metadata,
                        "type": "llm_response",
                        "generation_id": str(uuid.uuid4()),
                    },
                    usage_details=usage_details,
                )
                generation.end()
            self.log(f"LLM generation completed for chat_id: {chat_id}")
        except Exception as error:
            self.log(f"Failed to create LLM generation: {error}")
        finally:
            self._end_trace(chat_id)
            self._flush()

        return body
