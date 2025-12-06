"""
title: MLflow Tracing Filter Pipeline
author: Kristoffer Johansson
date: 2025-12-04
version: 0.0.1
license: MIT
description: A filter pipeline that creates traces in MLflow for LLM observability. Supports self-hosted MLflow and Databricks-hosted MLflow with PAT or Service Principal authentication (MLflow 3.x).
requirements: mlflow[databricks]>=3.0.0
"""

from typing import List, Optional
from dataclasses import dataclass, field
import os
import uuid
import json

from utils.pipelines.main import get_last_assistant_message
from pydantic import BaseModel
import mlflow
from mlflow import MlflowClient
from mlflow.entities import SpanType


def get_last_assistant_message_obj(messages: List[dict]) -> dict:
    """Retrieve the last assistant message object (for usage extraction)."""
    for message in reversed(messages):
        if message["role"] == "assistant":
            return message
    return {}


@dataclass
class ChatTrace:
    """Container for all trace-related data for a single chat."""
    request_id: str
    root_span: object
    model_info: dict = field(default_factory=dict)
    input_messages: list = field(default_factory=list)


class Pipeline:
    class Valves(BaseModel):
        pipelines: List[str] = []
        priority: int = 0
        # MLflow tracking URI - Databricks auto-detected from URL pattern
        # Examples: "https://xxx.cloud.databricks.com", "http://mlflow:5000"
        tracking_uri: str
        # Personal Access Token (works for both self-hosted MLflow and Databricks)
        token: Optional[str] = None
        # Service Principal OAuth M2M (Databricks only, with automatic token refresh)
        client_id: Optional[str] = None
        client_secret: Optional[str] = None
        # MLflow experiment ID (recommended for Databricks, takes precedence over name)
        experiment_id: Optional[str] = None
        # MLflow experiment name (alternative to experiment_id)
        experiment_name: Optional[str] = None
        debug: bool = False

    # Databricks URL patterns for auto-detection
    DATABRICKS_URL_PATTERNS = (
        ".cloud.databricks.com",   # AWS
        ".azuredatabricks.net",    # Azure
        ".gcp.databricks.com",     # GCP
    )

    # Tasks that should be traced (skip title generation, etc.)
    TRACED_TASKS = {"user_response", "llm_response"}

    def __init__(self):
        self.type = "filter"
        self.name = "MLflow Tracing Filter"

        self.valves = self.Valves(
            **{
                "pipelines": ["*"],
                "tracking_uri": os.getenv("MLFLOW_TRACKING_URI") or os.getenv("DATABRICKS_HOST", ""),
                "token": os.getenv("MLFLOW_TRACKING_TOKEN") or os.getenv("DATABRICKS_TOKEN"),
                "client_id": os.getenv("DATABRICKS_CLIENT_ID"),
                "client_secret": os.getenv("DATABRICKS_CLIENT_SECRET"),
                "experiment_id": os.getenv("MLFLOW_EXPERIMENT_ID"),
                "experiment_name": os.getenv("MLFLOW_EXPERIMENT_NAME"),
                "debug": os.getenv("DEBUG_MODE", "false").lower() == "true",
            }
        )

        # Client instance
        self.mlflow_client = None

        # Trace tracking (keyed by chat_id -> ChatTrace)
        self.chat_traces: dict[str, ChatTrace] = {}

        # Logging
        self.suppressed_logs = set()

    def log(self, message: str, suppress_repeats: bool = False):
        """Conditional debug logging."""
        if self.valves.debug:
            if suppress_repeats:
                if message in self.suppressed_logs:
                    return
                self.suppressed_logs.add(message)
            print(f"[DEBUG] {message}")

    async def on_startup(self):
        """Initialize MLflow client on server startup."""
        self.log(f"on_startup triggered for {__name__}")
        self.set_mlflow_client()

    async def on_shutdown(self):
        """Cleanup on server shutdown."""
        self.log(f"on_shutdown triggered for {__name__}")
        if self.mlflow_client:
            # End any pending traces
            for chat_id, trace in list(self.chat_traces.items()):
                try:
                    self.mlflow_client.end_trace(
                        trace_id=trace.request_id,
                        status="ERROR",
                        outputs={"error": "Server shutdown"},
                    )
                except Exception as e:
                    self.log(f"Failed to end trace {trace.request_id}: {e}")

            self.chat_traces.clear()

    async def on_valves_updated(self):
        """Reinitialize client when configuration changes."""
        self.log("Valves updated, resetting MLflow client")
        self.suppressed_logs.clear()
        self.set_mlflow_client()

    def _is_databricks_mode(self) -> bool:
        """Check if tracking_uri points to Databricks based on URL patterns."""
        uri = self.valves.tracking_uri.lower()
        return any(pattern in uri for pattern in self.DATABRICKS_URL_PATTERNS)

    def _setup_databricks_auth(self) -> str:
        """Configure Databricks authentication via environment variables.

        MLflow uses the Databricks SDK internally which handles OAuth M2M token
        refresh automatically when using environment variables.

        Returns:
            str: The authentication method used ('pat' or 'service_principal')

        Raises:
            ValueError: If no valid Databricks authentication is configured
        """
        os.environ["DATABRICKS_HOST"] = self.valves.tracking_uri

        # Service Principal OAuth M2M authentication
        # Clear PAT to avoid "more than one authorization method" error
        if self.valves.client_id and self.valves.client_secret:
            os.environ.pop("DATABRICKS_TOKEN", None)
            os.environ["DATABRICKS_CLIENT_ID"] = self.valves.client_id
            os.environ["DATABRICKS_CLIENT_SECRET"] = self.valves.client_secret
            return "service_principal"

        # PAT authentication
        # Clear Service Principal vars to avoid conflicts
        elif self.valves.token:
            os.environ.pop("DATABRICKS_CLIENT_ID", None)
            os.environ.pop("DATABRICKS_CLIENT_SECRET", None)
            os.environ["DATABRICKS_TOKEN"] = self.valves.token
            return "pat"

        raise ValueError("Databricks requires either token or client_id/client_secret")

    def _setup_mlflow_auth(self) -> str:
        """Configure self-hosted MLflow authentication.

        Returns:
            str: The authentication method used ('token' or 'none')
        """
        # Optional token authentication for self-hosted MLflow
        if self.valves.token:
            os.environ["MLFLOW_TRACKING_TOKEN"] = self.valves.token
            return "token"
        return "none"

    def set_mlflow_client(self):
        """Initialize MLflow client based on tracking_uri configuration.

        Databricks is auto-detected from URL patterns (*.cloud.databricks.com, etc.)

        Supports three modes:
        1. Self-hosted MLflow: tracking_uri is a non-Databricks URL (e.g., http://mlflow:5000)
        2. Databricks + PAT: tracking_uri is a Databricks URL with token
        3. Databricks + Service Principal: tracking_uri is a Databricks URL with client_id/secret
           (includes automatic token refresh)
        """
        if not self.valves.tracking_uri:
            print("MLflow tracking_uri not configured - tracing disabled")
            self.mlflow_client = None
            return

        try:
            if self._is_databricks_mode():
                # Databricks-hosted MLflow
                auth_method = self._setup_databricks_auth()
                self.log(f"Using Databricks with {auth_method} authentication")
                mlflow.set_tracking_uri("databricks")
            else:
                # Self-hosted MLflow
                auth_method = self._setup_mlflow_auth()
                self.log(f"Using self-hosted MLflow with {auth_method} authentication")
                mlflow.set_tracking_uri(self.valves.tracking_uri)

            # Pass tracking_uri explicitly to ensure client uses correct backend
            # (not the default local mlruns folder)
            self.mlflow_client = MlflowClient(tracking_uri=mlflow.get_tracking_uri())

            # Set experiment if configured (experiment_id takes precedence)
            if self.valves.experiment_id:
                mlflow.set_experiment(experiment_id=self.valves.experiment_id)
                self.log(f"Set experiment by ID: {self.valves.experiment_id}")
            elif self.valves.experiment_name:
                mlflow.set_experiment(experiment_name=self.valves.experiment_name)
                self.log(f"Set experiment by name: {self.valves.experiment_name}")

            # Validate authentication by testing a simple API call
            try:
                self.mlflow_client.search_experiments(max_results=1)
                self.log("MLflow client initialized and authenticated successfully")
            except Exception as auth_error:
                print(f"MLflow authentication failed: {auth_error}")
                self.mlflow_client = None
                return

        except ValueError as e:
            print(f"MLflow configuration error: {e}")
        except Exception as e:
            print(
                f"MLflow error: {e}. Please check your configuration in the pipeline settings."
            )

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        """Capture user input and start MLflow trace."""
        if self.valves.debug:
            self.log(f"Inlet received request: {json.dumps(body, indent=2)}")
        self.log(f"Inlet function called with user: {user}")

        if not self.mlflow_client:
            self.log("[WARNING] MLflow client not initialized - skipping tracing")
            return body

        # Extract metadata
        metadata = body.get("metadata", {})

        task_name = metadata.get("task", "user_response")
        if task_name not in self.TRACED_TASKS:
            self.log(f"Skipping {task_name} task")
            return body

        # Validate required keys
        required_keys = ["model", "messages"]
        missing_keys = [key for key in required_keys if key not in body]
        if missing_keys:
            error_message = (
                f"Error: Missing keys in the request body: {', '.join(missing_keys)}"
            )
            self.log(error_message)
            raise ValueError(error_message)

        # Extract chat_id
        chat_id = metadata.get("chat_id", str(uuid.uuid4()))

        # Handle temporary chats
        if chat_id == "local":
            session_id = metadata.get("session_id")
            chat_id = f"temporary-session-{session_id}"

        metadata["chat_id"] = chat_id
        body["metadata"] = metadata

        # Build model info
        model_id = body.get("model")
        model_info = metadata.get("model", {})
        model_data = {
            "id": model_id,
            "name": model_info.get("name", model_id) if isinstance(model_info, dict) else model_id,
        }

        # Build attributes
        user_email = user.get("email") if user else None
        attributes = {
            "user_id": user_email or "anonymous",
            "chat_id": chat_id,
            "interface": "open-webui",
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": model_id,
            "tag.open-webui": True,
        }

        # Create new trace
        if chat_id not in self.chat_traces:
            self.log(f"Creating new trace for chat_id: {chat_id}")
            try:
                root_span = self.mlflow_client.start_trace(
                    name=f"chat:{chat_id}",
                    span_type=SpanType.CHAIN,
                    inputs={"messages": body.get("messages", [])},
                    attributes=attributes,
                )
                self.chat_traces[chat_id] = ChatTrace(
                    request_id=root_span.request_id,
                    root_span=root_span,
                    model_info=model_data,
                    input_messages=body.get("messages", []),
                )
                self.log(f"Trace created with request_id: {root_span.request_id}")
            except Exception as e:
                self.log(f"Failed to create trace: {e}")
        else:
            self.log(f"Trace already exists for chat_id: {chat_id}")

        return body

    async def outlet(self, body: dict, user: Optional[dict] = None) -> dict:
        """Capture LLM output and complete MLflow trace."""
        self.log("Outlet function called")

        if not self.mlflow_client:
            self.log("[WARNING] MLflow client not initialized - skipping tracing")
            return body

        # Skip non-chat tasks
        metadata = body.get("metadata", {})
        task_name = metadata.get("task", "llm_response")
        if task_name not in self.TRACED_TASKS:
            self.log(f"Skipping {task_name} task")
            return body

        chat_id = body.get("chat_id")

        # Handle temporary chats
        if chat_id == "local":
            session_id = body.get("session_id")
            chat_id = f"temporary-session-{session_id}"

        if chat_id not in self.chat_traces:
            self.log(f"[WARNING] No trace found for chat_id: {chat_id}")
            return body

        trace = self.chat_traces[chat_id]

        # Extract assistant message
        assistant_message = get_last_assistant_message(body["messages"])
        assistant_message_obj = get_last_assistant_message_obj(body["messages"])

        # Extract token usage
        usage = None
        if assistant_message_obj:
            info = assistant_message_obj.get("usage", {})
            if isinstance(info, dict):
                input_tokens = info.get("prompt_eval_count") or info.get("prompt_tokens")
                output_tokens = info.get("eval_count") or info.get("completion_tokens")
                if input_tokens is not None and output_tokens is not None:
                    usage = {
                        "prompt_tokens": input_tokens,
                        "completion_tokens": output_tokens,
                        "total_tokens": input_tokens + output_tokens,
                    }
                    self.log(f"Usage data extracted: {usage}")

        try:
            # Create LLM span for the generation
            llm_attributes = {
                "model": trace.model_info.get("id"),
                "model_name": trace.model_info.get("name"),
            }
            if usage:
                llm_attributes["prompt_tokens"] = usage["prompt_tokens"]
                llm_attributes["completion_tokens"] = usage["completion_tokens"]
                llm_attributes["total_tokens"] = usage["total_tokens"]

            llm_span = self.mlflow_client.start_span(
                name="llm_generation",
                trace_id=trace.request_id,
                parent_id=trace.root_span.span_id,
                span_type=SpanType.CHAT_MODEL,
                inputs={"messages": trace.input_messages},
                attributes=llm_attributes,
            )

            # End LLM span
            self.mlflow_client.end_span(
                trace_id=trace.request_id,
                span_id=llm_span.span_id,
                outputs={"response": assistant_message},
                status="OK",
            )
            self.log(f"LLM span ended for chat_id: {chat_id}")

            # End root trace
            self.mlflow_client.end_trace(
                trace_id=trace.request_id,
                outputs={"response": assistant_message},
                status="OK",
            )
            self.log(f"Trace ended for chat_id: {chat_id}")

        except Exception as e:
            self.log(f"Error completing trace: {e}")
            try:
                self.mlflow_client.end_trace(
                    trace_id=trace.request_id,
                    status="ERROR",
                    outputs={"error": str(e)},
                )
            except Exception:
                pass

        finally:
            self.chat_traces.pop(chat_id, None)

        return body
