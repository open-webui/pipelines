"""
title: Langfuse Filter Pipeline for v3
author: open-webui
date: 2025-07-31
version: 0.0.1
license: MIT
description: A filter pipeline that uses Langfuse v3.
requirements: langfuse>=3.0.0
"""

from typing import List, Optional
import os
import uuid
import json


from utils.pipelines.main import get_last_assistant_message
from pydantic import BaseModel
from langfuse import Langfuse


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
            try:
                # End all active traces
                for chat_id, trace in self.chat_traces.items():
                    try:
                        trace.end()
                        self.log(f"Ended trace for chat_id: {chat_id}")
                    except Exception as e:
                        self.log(f"Failed to end trace for {chat_id}: {e}")

                self.chat_traces.clear()
                self.langfuse.flush()
                self.log("Langfuse data flushed on shutdown")
            except Exception as e:
                self.log(f"Failed to flush Langfuse data: {e}")

    async def on_valves_updated(self):
        self.log("Valves updated, resetting Langfuse client.")
        self.set_langfuse()

    def set_langfuse(self):
        try:
            self.log(f"Initializing Langfuse with host: {self.valves.host}")
            self.log(
                f"Secret key set: {'Yes' if self.valves.secret_key and self.valves.secret_key != 'your-secret-key-here' else 'No'}"
            )
            self.log(
                f"Public key set: {'Yes' if self.valves.public_key and self.valves.public_key != 'your-public-key-here' else 'No'}"
            )

            # Initialize Langfuse client for v3.2.1
            self.langfuse = Langfuse(
                secret_key=self.valves.secret_key,
                public_key=self.valves.public_key,
                host=self.valves.host,
                debug=self.valves.debug,
            )

            # Test authentication
            try:
                self.langfuse.auth_check()
                self.log(
                    f"Langfuse client initialized and authenticated successfully. Connected to host: {self.valves.host}")

            except Exception as e:
                self.log(f"Auth check failed: {e}")
                self.log(f"Failed host: {self.valves.host}")
                self.langfuse = None
                return

        except Exception as auth_error:
            if (
                "401" in str(auth_error)
                or "unauthorized" in str(auth_error).lower()
                or "credentials" in str(auth_error).lower()
            ):
                self.log(f"Langfuse credentials incorrect: {auth_error}")
                self.langfuse = None
                return
        except Exception as e:
            self.log(f"Langfuse initialization error: {e}")
            self.langfuse = None

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
        self.log("Langfuse Filter INLET called")

        # Check Langfuse client status
        if not self.langfuse:
            self.log("[WARNING] Langfuse client not initialized - Skipped")
            return body

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

            try:
                # Create trace using Langfuse v3 API with complete data
                trace_metadata = {
                    **metadata,
                    "user_id": user_email,
                    "session_id": chat_id,
                    "interface": "open-webui",
                }
                
                # Create trace with all necessary information
                trace = self.langfuse.start_span(
                    name=f"chat:{chat_id}",
                    input=body,
                    metadata=trace_metadata
                )

                # Set additional trace attributes
                trace.update_trace(
                    user_id=user_email,
                    session_id=chat_id,
                    tags=tags_list if tags_list else None,
                    input=body,
                    metadata=trace_metadata,
                )

                self.chat_traces[chat_id] = trace
                self.log(f"Successfully created trace for chat_id: {chat_id}")
            except Exception as e:
                self.log(f"Failed to create trace: {e}")
                return body
        else:
            trace = self.chat_traces[chat_id]
            self.log(f"Reusing existing trace for chat_id: {chat_id}")
            # Update trace with current metadata and tags
            trace_metadata = {
                **metadata,
                "user_id": user_email,
                "session_id": chat_id,
                "interface": "open-webui",
            }
            trace.update_trace(
                tags=tags_list if tags_list else None,
                metadata=trace_metadata,
            )

        # Update metadata with type
        metadata["type"] = task_name
        metadata["interface"] = "open-webui"

        # Log user input as event
        try:
            trace = self.chat_traces[chat_id]
            
            # Create complete event metadata
            event_metadata = {
                **metadata,
                "type": "user_input",
                "interface": "open-webui",
                "user_id": user_email,
                "session_id": chat_id,
                "event_id": str(uuid.uuid4()),
            }
            
            event_span = trace.start_span(
                name=f"user_input:{str(uuid.uuid4())}",
                metadata=event_metadata,
                input=body["messages"],
            )
            event_span.end()
            self.log(f"User input event logged for chat_id: {chat_id}")
        except Exception as e:
            self.log(f"Failed to log user input event: {e}")

        return body

    async def outlet(self, body: dict, user: Optional[dict] = None) -> dict:
        self.log("Langfuse Filter OUTLET called")

        # Check Langfuse client status
        if not self.langfuse:
            self.log("[WARNING] Langfuse client not initialized - Skipped")
            return body

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

        self.chat_traces[chat_id]

        assistant_message = get_last_assistant_message(body["messages"])
        assistant_message_obj = get_last_assistant_message_obj(body["messages"])

        usage_details = None
        if assistant_message_obj:
            info = assistant_message_obj.get("usage", {})
            if isinstance(info, dict):
                input_tokens = info.get("prompt_eval_count") or info.get("prompt_tokens")
                output_tokens = info.get("eval_count") or info.get("completion_tokens")
                if input_tokens is not None and output_tokens is not None:
                    # Langfuse v3 token aggregation expects usage_details.
                    usage_details = {
                        "input": int(input_tokens),
                        "output": int(output_tokens),
                        "total": int(input_tokens) + int(output_tokens),
                    }
                    self.log(f"Usage data extracted: {usage_details}")

        # Update the trace with complete output information
        trace = self.chat_traces[chat_id]
        
        metadata["type"] = task_name
        metadata["interface"] = "open-webui"
        
        # Create complete trace metadata with all information
        complete_trace_metadata = {
            **metadata,
            "user_id": user.get("email") if user else None,
            "session_id": chat_id,
            "interface": "open-webui",
            "task": task_name,
        }
        
        # Update trace with output and complete metadata
        trace.update_trace(
            output=assistant_message,
            metadata=complete_trace_metadata,
            tags=tags_list if tags_list else None,
        )

        # Outlet: Always create LLM generation (this is the LLM response)
        # Determine which model value to use based on the use_model_name valve
        model_id = self.model_names.get(chat_id, {}).get("id", body.get("model"))
        model_name = self.model_names.get(chat_id, {}).get("name", "unknown")

        # Pick primary model identifier based on valve setting
        model_value = (
            model_name
            if self.valves.use_model_name_instead_of_id_for_generation
            else model_id
        )

        # Add both values to metadata regardless of valve setting
        metadata["model_id"] = model_id
        metadata["model_name"] = model_name

        # Create LLM generation for the response
        try:
            trace = self.chat_traces[chat_id]
            
            # Create complete generation metadata
            generation_metadata = {
                **complete_trace_metadata,
                "type": "llm_response",
                "model_id": model_id,
                "model_name": model_name,
                "generation_id": str(uuid.uuid4()),
            }
            
            generation = trace.start_generation(
                name=f"llm_response:{str(uuid.uuid4())}",
                model=model_value,
                input=body["messages"],
                output=assistant_message,
                metadata=generation_metadata,
            )

            # Update with usage if available
            if usage_details:
                generation.update(usage_details=usage_details)

            generation.end()
            self.log(f"LLM generation completed for chat_id: {chat_id}")
        except Exception as e:
            self.log(f"Failed to create LLM generation: {e}")

        # Flush data to Langfuse
        try:
            if self.langfuse:
                self.langfuse.flush()
                self.log("Langfuse data flushed")
        except Exception as e:
            self.log(f"Failed to flush Langfuse data: {e}")

        return body
