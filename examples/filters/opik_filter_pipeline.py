"""
title: Opik Filter Pipeline
author: open-webui
date: 2025-03-12
version: 1.1
license: MIT
description: A filter pipeline that uses Opik for LLM observability with improved error handling.
requirements: opik
"""

from typing import List, Optional
import os
import uuid
import json
import time

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

    def cleanup_stale_spans(self, chat_id: str):
        """Clean up any existing span for a chat_id to prepare for a new one"""
        if chat_id in self.chat_spans:
            try:
                existing_span = self.chat_spans[chat_id]
                # End the previous span before creating a new one
                existing_span.end(output={"status": "interrupted", "reason": "new_message_received"})
                self.log(f"Ended previous span for chat_id: {chat_id}")
            except Exception as e:
                self.log(f"Warning: Could not end existing span for {chat_id}: {e}")
            finally:
                # Always remove from tracking
                self.chat_spans.pop(chat_id, None)

    def cleanup_orphaned_traces(self, max_count: int = 100):
        """Clean up traces if we have too many active ones"""
        if len(self.chat_traces) > max_count:
            self.log(f"Too many active traces ({len(self.chat_traces)}), cleaning up oldest ones")
            # Clean up oldest traces (simple FIFO approach)
            chat_ids_to_remove = list(self.chat_traces.keys())[:len(self.chat_traces) - max_count + 10]
            for chat_id in chat_ids_to_remove:
                try:
                    if chat_id in self.chat_spans:
                        span = self.chat_spans[chat_id]
                        span.end(output={"status": "cleanup", "reason": "too_many_active_traces"})
                except:
                    pass
                try:
                    if chat_id in self.chat_traces:
                        trace = self.chat_traces[chat_id]
                        trace.end(output={"status": "cleanup", "reason": "too_many_active_traces"})
                except:
                    pass
                self.chat_traces.pop(chat_id, None)
                self.chat_spans.pop(chat_id, None)

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        """
        Inlet handles the incoming request (usually a user message).
        - If no trace exists yet for this chat_id, we create a new trace.
        - If a trace does exist, we reuse it and create a new span for the new user message.
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
            # Generate unique chat_id with timestamp for extra uniqueness
            chat_id = f"{uuid.uuid4()}-{int(time.time() * 1000)}"
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

        # Periodic cleanup to prevent memory leaks
        self.cleanup_orphaned_traces()

        # FIXED: Check if trace already exists
        trace = None
        if chat_id in self.chat_traces:
            # Reuse existing trace for continuing conversation
            trace = self.chat_traces[chat_id]
            self.log(f"Reusing existing trace for chat_id: {chat_id}")
            
            # Clean up any existing span to prepare for new one
            self.cleanup_stale_spans(chat_id)
        else:
            # Create a new trace for new conversation
            self.log(f"Creating new chat trace for chat_id: {chat_id}")
            
            try:
                # Body copy for trace
                trace_body = body.copy()

                # Extract metadata from body
                trace_metadata = trace_body.pop("metadata", {})
                trace_metadata.update({"chat_id": chat_id, "user_id": user_email})

                # We don't need the model at the trace level
                trace_body.pop("model", None)

                trace_payload = {
                    "name": f"{__name__}",
                    "input": trace_body,
                    "metadata": trace_metadata,
                    "thread_id": chat_id,
                }

                if self.valves.debug:
                    print(f"[DEBUG] Opik trace request: {json.dumps(trace_payload, indent=2)}")

                trace = self.opik.trace(**trace_payload)
                self.chat_traces[chat_id] = trace
                self.log(f"New trace created for chat_id: {chat_id}")

            except Exception as e:
                self.log(f"Error creating Opik trace for chat_id {chat_id}: {e}")
                # Continue without Opik logging for this request
                return body

        # Create a new span (whether trace is new or existing)
        try:
            # Body copy for span
            span_body = body.copy()

            span_metadata = metadata.copy()
            span_metadata.update({"interface": "open-webui", "user_id": user_email})

            # Extract the model from body
            span_body.pop("model", None)
            # We don't need the metadata in the input for the span
            span_body.pop("metadata", None)

            # Extract the model and provider from metadata
            model = span_metadata.get("model", {}).get("id", None)
            provider = span_metadata.get("model", {}).get("owned_by", None)

            # Generate unique span name with timestamp
            span_name = f"{chat_id}-{int(time.time() * 1000)}"

            span_payload = {
                "name": span_name,
                "model": model,
                "provider": provider,
                "input": span_body,
                "metadata": span_metadata,
                "type": "llm",
            }

            if self.valves.debug:
                print(f"[DEBUG] Opik span request: {json.dumps(span_payload, indent=2)}")

            span = trace.span(**span_payload)
            self.chat_spans[chat_id] = span
            self.log(f"New span created for chat_id: {chat_id}")

        except Exception as e:
            self.log(f"Error creating Opik span for chat_id {chat_id}: {e}")
            # Don't fail the request, just log the error

        return body

    async def outlet(self, body: dict, user: Optional[dict] = None) -> dict:
        """
        Outlet handles the response body (usually the assistant message).
        It will finalize/end the span created for the user request.
        """
        self.log(f"Outlet function called with body: {body}")

        chat_id = body.get("chat_id")

        # If no span exists, we can't log this response
        if chat_id not in self.chat_spans:
            self.log(
                f"[WARNING] No active span found for chat_id: {chat_id}, response won't be logged."
            )
            return body

        span = self.chat_spans[chat_id]

        try:
            # Body copy for span
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
            self.log(f"Span ended for chat_id: {chat_id}")

        except Exception as e:
            self.log(f"Error ending Opik span for chat_id {chat_id}: {e}")
            # Try to end gracefully even if there are errors
            try:
                span.end(output={"status": "error", "error": str(e)})
            except:
                pass

        finally:
            # Clean up the span reference (but keep the trace for potential future messages)
            self.chat_spans.pop(chat_id, None)
            self.log(f"Cleaned up span reference for chat_id: {chat_id}")

        # NOTE: We deliberately DON'T clean up the trace here, as it should persist
        # for the duration of the conversation. Traces will be cleaned up by:
        # 1. The cleanup_orphaned_traces method when there are too many
        # 2. Server restart/shutdown
        # 3. Manual cleanup if needed

        return body
