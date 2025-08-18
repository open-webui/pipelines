"""
title: Opik Filter Pipeline
author: open-webui
date: 2025-03-12
version: 1.3
license: MIT
description: A comprehensive filter pipeline that uses Opik for LLM observability with improved error handling and universal usage tracking. Supports token counting and billing data for all major LLM providers including Anthropic (Claude), OpenAI (GPT), Google (Gemini), Meta (Llama), Mistral, Cohere, and others.
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

    def detect_provider_type(self, body: dict, metadata: dict) -> str:
        """Detect the LLM provider type based on model name and response structure"""
        model_info = metadata.get("model", {})
        model_id = model_info.get("id", "").lower()
        model_name = body.get("model", "").lower()
        
        # Check model names/IDs for provider detection
        if any(x in model_id or x in model_name for x in ["claude", "anthropic"]):
            return "anthropic"
        elif any(x in model_id or x in model_name for x in ["gpt", "openai", "o1"]):
            return "openai"
        elif any(x in model_id or x in model_name for x in ["gemini", "palm", "bard", "google"]):
            return "google"
        elif any(x in model_id or x in model_name for x in ["llama", "meta"]):
            return "meta"
        elif any(x in model_id or x in model_name for x in ["mistral"]):
            return "mistral"
        elif any(x in model_id or x in model_name for x in ["cohere"]):
            return "cohere"
        
        # Check response structure for provider hints
        if "usage" in body and "input_tokens" in body.get("usage", {}):
            return "anthropic"
        elif "usage" in body and "prompt_tokens" in body.get("usage", {}):
            return "openai"
        elif "usageMetadata" in body:
            return "google"
        
        return "unknown"

    def extract_usage_data(self, body: dict, metadata: dict = None) -> Optional[dict]:
        """Extract token usage data with support for multiple API providers (Anthropic, OpenAI, Gemini, etc.)"""
        if metadata is None:
            metadata = {}
            
        provider = self.detect_provider_type(body, metadata)
        self.log(f"Detected provider: {provider}")
        
        usage = None
        
        # Method 1: Check for usage in response body (multiple provider formats)
        if "usage" in body and isinstance(body["usage"], dict):
            usage_data = body["usage"]
            self.log(f"Found usage data in response body: {usage_data}")
            
            # Anthropic API format: input_tokens, output_tokens
            input_tokens = usage_data.get("input_tokens")
            output_tokens = usage_data.get("output_tokens")
            
            # OpenAI API format: prompt_tokens, completion_tokens
            if input_tokens is None or output_tokens is None:
                input_tokens = usage_data.get("prompt_tokens")
                output_tokens = usage_data.get("completion_tokens")
            
            # Some variations use different field names
            if input_tokens is None or output_tokens is None:
                input_tokens = usage_data.get("promptTokens") or usage_data.get("prompt_token_count")
                output_tokens = usage_data.get("completionTokens") or usage_data.get("completion_token_count")
            
            if input_tokens is not None and output_tokens is not None:
                total_tokens = usage_data.get("total_tokens") or usage_data.get("totalTokens") or (input_tokens + output_tokens)
                usage = {
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                    "total_tokens": total_tokens,
                }
                self.log(f"Extracted usage data from response body: {usage}")
                return usage
        
        # Method 2: Check for Gemini API format (usageMetadata)
        if "usageMetadata" in body and isinstance(body["usageMetadata"], dict):
            gemini_usage = body["usageMetadata"]
            self.log(f"Found Gemini usage metadata: {gemini_usage}")
            
            input_tokens = (
                gemini_usage.get("promptTokenCount") or
                gemini_usage.get("prompt_token_count") or
                gemini_usage.get("inputTokens")
            )
            output_tokens = (
                gemini_usage.get("candidatesTokenCount") or
                gemini_usage.get("candidates_token_count") or
                gemini_usage.get("outputTokens") or
                gemini_usage.get("completionTokens")
            )
            total_tokens = (
                gemini_usage.get("totalTokenCount") or
                gemini_usage.get("total_token_count") or
                gemini_usage.get("totalTokens")
            )
            
            if input_tokens is not None and output_tokens is not None:
                if total_tokens is None:
                    total_tokens = input_tokens + output_tokens
                usage = {
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                    "total_tokens": total_tokens,
                }
                self.log(f"Extracted Gemini usage data: {usage}")
                return usage
        
        # Method 3: Check assistant message for usage data (various formats)
        assistant_message_obj = get_last_assistant_message_obj(body.get("messages", []))
        if assistant_message_obj:
            message_usage = assistant_message_obj.get("usage", {})
            self.log(f"Assistant message usage: {message_usage}")
            
            if isinstance(message_usage, dict):
                # Try multiple field name variations for different providers
                input_tokens = (
                    message_usage.get("input_tokens") or          # Anthropic
                    message_usage.get("prompt_tokens") or         # OpenAI
                    message_usage.get("prompt_eval_count") or     # Some local models
                    message_usage.get("promptTokenCount") or      # Gemini variants
                    message_usage.get("prompt_token_count")       # Alternative naming
                )
                output_tokens = (
                    message_usage.get("output_tokens") or         # Anthropic
                    message_usage.get("completion_tokens") or     # OpenAI
                    message_usage.get("eval_count") or            # Some local models
                    message_usage.get("candidatesTokenCount") or  # Gemini variants
                    message_usage.get("completion_token_count")   # Alternative naming
                )
                total_tokens = (
                    message_usage.get("total_tokens") or
                    message_usage.get("totalTokens") or
                    message_usage.get("totalTokenCount")
                )
                
                if input_tokens is not None and output_tokens is not None:
                    if total_tokens is None:
                        total_tokens = input_tokens + output_tokens
                    usage = {
                        "prompt_tokens": input_tokens,
                        "completion_tokens": output_tokens,
                        "total_tokens": total_tokens,
                    }
                    self.log(f"Extracted message-level usage data: {usage}")
                    return usage
        
        # Method 4: Check for usage at individual message level (some APIs put it there)
        if "messages" in body and isinstance(body["messages"], list):
            for message in reversed(body["messages"]):
                if message.get("role") == "assistant":
                    # Check multiple possible usage field locations
                    usage_sources = [
                        message.get("usage", {}),
                        message.get("usageMetadata", {}),
                        message.get("metadata", {}).get("usage", {}) if message.get("metadata") else {}
                    ]
                    
                    for msg_usage in usage_sources:
                        if isinstance(msg_usage, dict) and msg_usage:
                            self.log(f"Found message usage: {msg_usage}")
                            
                            input_tokens = (
                                msg_usage.get("input_tokens") or
                                msg_usage.get("prompt_tokens") or
                                msg_usage.get("promptTokenCount") or
                                msg_usage.get("prompt_eval_count")
                            )
                            output_tokens = (
                                msg_usage.get("output_tokens") or
                                msg_usage.get("completion_tokens") or
                                msg_usage.get("candidatesTokenCount") or
                                msg_usage.get("eval_count")
                            )
                            total_tokens = (
                                msg_usage.get("total_tokens") or
                                msg_usage.get("totalTokens") or
                                msg_usage.get("totalTokenCount")
                            )
                            
                            if input_tokens is not None and output_tokens is not None:
                                if total_tokens is None:
                                    total_tokens = input_tokens + output_tokens
                                usage = {
                                    "prompt_tokens": input_tokens,
                                    "completion_tokens": output_tokens,
                                    "total_tokens": total_tokens,
                                }
                                self.log(f"Extracted individual message usage: {usage}")
                                return usage
        
        # Method 5: Check alternative response structures (some proxies/wrappers)
        for alt_key in ["token_usage", "billing", "cost_info", "metrics"]:
            if alt_key in body and isinstance(body[alt_key], dict):
                alt_usage = body[alt_key]
                self.log(f"Found alternative usage data in {alt_key}: {alt_usage}")
                
                input_tokens = (
                    alt_usage.get("input_tokens") or
                    alt_usage.get("prompt_tokens") or
                    alt_usage.get("input") or
                    alt_usage.get("prompt")
                )
                output_tokens = (
                    alt_usage.get("output_tokens") or
                    alt_usage.get("completion_tokens") or
                    alt_usage.get("output") or
                    alt_usage.get("completion")
                )
                
                if input_tokens is not None and output_tokens is not None:
                    total_tokens = alt_usage.get("total_tokens") or alt_usage.get("total") or (input_tokens + output_tokens)
                    usage = {
                        "prompt_tokens": input_tokens,
                        "completion_tokens": output_tokens,
                        "total_tokens": total_tokens,
                    }
                    self.log(f"Extracted alternative usage data: {usage}")
                    return usage
        
        self.log("No usage data found in any expected location")
        if self.valves.debug:
            # Log the full body structure to help debug
            self.log(f"Full response body keys: {list(body.keys())}")
            if "messages" in body and body["messages"]:
                last_message = body["messages"][-1] if body["messages"] else {}
                self.log(f"Last message keys: {list(last_message.keys()) if isinstance(last_message, dict) else 'Not a dict'}")
        
        return None

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

            # FIXED: Extract usage data using improved method that supports multiple providers
            metadata = body.get("metadata", {})
            usage = self.extract_usage_data(body, metadata)
            
            # Add provider and model information to usage data for better analytics
            if usage:
                provider = self.detect_provider_type(body, metadata)
                model_info = metadata.get("model", {})
                
                # Enhance usage data with provider context
                usage.update({
                    "provider": provider,
                    "model_id": model_info.get("id", "unknown"),
                    "model_name": model_info.get("name", "unknown"),
                })
                self.log(f"Enhanced usage data with provider info: {usage}")
            
            if usage:
                self.log(f"Successfully extracted usage data: {usage}")
            else:
                self.log("No usage data found - this might indicate an API integration issue")

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
