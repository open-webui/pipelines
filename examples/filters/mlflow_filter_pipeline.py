"""
title: MLflow Filter Pipeline for Open WebUI
author: axc888
date: 2025-09-28
version: 0.0.1
license: MIT
description: A filter pipeline that uses MLflow for tracking conversations, model interactions, model performance metrics and usage analytics.
 Supports both per-conversation and per-interaction tracking modes with detailed metrics and artifacts.
requirements: mlflow>=2.0.0, requests>=2.25.0
"""

from typing import List, Optional
import os
import uuid
import json
import time
from datetime import datetime

from utils.pipelines.main import get_last_assistant_message
from pydantic import BaseModel
import mlflow
import mlflow.tracking


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
        tracking_uri: str
        experiment_name: str
        # Controls whether task names are added as tags
        insert_tags: bool = True
        # Controls whether to use model name instead of model ID for logging
        use_model_name_instead_of_id: bool = False
        # Controls whether to create separate runs for each interaction or one run per chat
        separate_runs_per_interaction: bool = False
        # Connection timeout for MLflow server health checks
        connection_timeout: int = 5
        debug: bool = False

    def __init__(self):
        self.type = "filter"
        self.name = "MLflow Conversation Tracker"

        self.valves = self.Valves(
            **{
                "pipelines": ["*"],
                "tracking_uri": os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"),
                "experiment_name": os.getenv("MLFLOW_EXPERIMENT_NAME", "open-webui-experiments"),
                "use_model_name_instead_of_id": os.getenv("USE_MODEL_NAME", "false").lower() == "true",
                "separate_runs_per_interaction": os.getenv("SEPARATE_RUNS", "false").lower() == "true",
                "debug": os.getenv("DEBUG_MODE", "false").lower() == "true",
            }
        )

        # Initialize MLflow components
        self.mlflow_client = None
        self.experiment_id = None
        self.chat_runs = {}  # Track active runs for each chat
        self.suppressed_logs = set()
        self.model_names = {}  # Store model names for each chat

    def log(self, message: str, suppress_repeats: bool = False):
        """Log debug messages if debug mode is enabled."""
        if self.valves.debug:
            if suppress_repeats:
                if message in self.suppressed_logs:
                    return
                self.suppressed_logs.add(message)
            print(f"[MLflow Pipeline] {message}")

    async def on_startup(self):
        """Initialize MLflow connection on pipeline startup."""
        self.log(f"Starting MLflow Pipeline")
        self.setup_mlflow()

    async def on_shutdown(self):
        """Clean up MLflow connections on pipeline shutdown."""
        self.log("Shutting down MLflow Pipeline")
        if self.mlflow_client:
            try:
                # End all active runs
                for chat_id, run_info in self.chat_runs.items():
                    try:
                        if run_info and run_info.get("run_id"):
                            mlflow.end_run()
                            self.log(f"Ended MLflow run for chat_id: {chat_id}")
                    except Exception as e:
                        self.log(f"Failed to end run for {chat_id}: {e}")

                self.chat_runs.clear()
                self.log("MLflow runs ended on shutdown")
            except Exception as e:
                self.log(f"Failed to end MLflow runs: {e}")

    async def on_valves_updated(self):
        self.log("Valves updated, resetting MLflow client.")
        self.setup_mlflow()

    def setup_mlflow(self):
        """Initialize MLflow client and experiment."""
        try:
            self.log(f"Connecting to MLflow at: {self.valves.tracking_uri}")
            
            # Set tracking URI
            mlflow.set_tracking_uri(self.valves.tracking_uri)
            self.mlflow_client = mlflow.tracking.MlflowClient()
            
            # Test connection with timeout
            try:
                import requests
                from urllib.parse import urlparse
                
                # Parse URI to test connection
                parsed_uri = urlparse(self.valves.tracking_uri)
                test_url = f"{parsed_uri.scheme}://{parsed_uri.netloc}/health"
                
                # Quick connection test with configurable timeout
                response = requests.get(test_url, timeout=self.valves.connection_timeout)
                self.log(f"MLflow server health check passed: {response.status_code}")
                
            except Exception as conn_error:
                self.log(f"MLflow server connection test failed: {conn_error}")
                self.log("MLflow server may not be running. Pipeline will continue without tracking.")
                self.mlflow_client = None
                return
            
            # Create or get experiment
            try:
                experiment = mlflow.get_experiment_by_name(self.valves.experiment_name)
                if experiment is None:
                    self.experiment_id = mlflow.create_experiment(self.valves.experiment_name)
                    self.log(f"Created new MLflow experiment: {self.valves.experiment_name}")
                else:
                    self.experiment_id = experiment.experiment_id
                    self.log(f"Using existing MLflow experiment: {self.valves.experiment_name}")
                
                mlflow.set_experiment(self.valves.experiment_name)
                self.log(f"MLflow setup successful. Experiment ID: {self.experiment_id}")
                
            except Exception as e:
                self.log(f"Failed to setup MLflow experiment: {e}")
                self.log("Check if MLflow server is running and accessible.")
                self.mlflow_client = None
                return

        except Exception as e:
            self.log(f"MLflow initialization error: {e}")
            self.log("Pipeline will continue without MLflow tracking.")
            self.mlflow_client = None

    def _build_tags(self, task_name: str) -> dict:
        """Build tags dictionary for MLflow runs."""
        tags_dict = {}
        if self.valves.insert_tags:
            # Always add source tag
            tags_dict["source"] = "open-webui"
            # Add the task_name if it's not one of the excluded defaults
            if task_name not in ["user_response", "llm_response"]:
                tags_dict["task_type"] = task_name
        return tags_dict

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        self.log("MLflow Filter INLET called")

        # Check MLflow client status
        if not self.mlflow_client:
            self.log("[WARNING] MLflow client not initialized - Skipped")
            return body

        self.log(f"Inlet function called with body keys: {list(body.keys())} and user: {user}")

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
        tags_dict = self._build_tags(task_name)

        # Create or get MLflow run for this chat
        if chat_id not in self.chat_runs or not self.chat_runs[chat_id]:
            self.log(f"Creating new MLflow run for chat_id: {chat_id}")

            try:
                # Start new MLflow run
                run = mlflow.start_run(
                    experiment_id=self.experiment_id,
                    run_name=f"chat-{chat_id}",
                    tags={
                        **tags_dict,
                        "chat_id": chat_id,
                        "user_id": user_email or "unknown",
                        "interface": "open-webui",
                        "run_type": "conversation"
                    }
                )

                self.chat_runs[chat_id] = {
                    "run_id": run.info.run_id,
                    "start_time": time.time(),
                    "interaction_count": 0
                }

                # Log initial parameters
                mlflow.log_params({
                    "chat_id": chat_id,
                    "user_email": user_email or "unknown",
                    "model_id": model_id,
                    "interface": "open-webui",
                    "task_type": task_name
                })

                self.log(f"Successfully created MLflow run for chat_id: {chat_id}, run_id: {run.info.run_id}")
                
                # If we want separate runs per interaction, end this run and start a new one for each interaction
                if self.valves.separate_runs_per_interaction:
                    mlflow.end_run()
                    
            except Exception as e:
                self.log(f"Failed to create MLflow run: {e}")
                return body
        else:
            run_info = self.chat_runs[chat_id]
            self.log(f"Using existing MLflow run for chat_id: {chat_id}, run_id: {run_info['run_id']}")

        # Log user input
        try:
            run_info = self.chat_runs[chat_id]
            run_info["interaction_count"] += 1
            interaction_num = run_info["interaction_count"]
            
            if self.valves.separate_runs_per_interaction:
                # Start a new run for this specific interaction
                interaction_run = mlflow.start_run(
                    experiment_id=self.experiment_id,
                    run_name=f"chat-{chat_id}-interaction-{interaction_num}",
                    tags={
                        **tags_dict,
                        "chat_id": chat_id,
                        "interaction_number": str(interaction_num),
                        "user_id": user_email or "unknown",
                        "interface": "open-webui",
                        "run_type": "interaction"
                    }
                )
                
                # Log parameters for this interaction
                mlflow.log_params({
                    "chat_id": chat_id,
                    "interaction_number": interaction_num,
                    "user_email": user_email or "unknown",
                    "model_id": model_id,
                    "interface": "open-webui",
                    "task_type": task_name
                })
            
            # Log user input as text artifact
            user_messages = [msg for msg in body["messages"] if msg["role"] == "user"]
            if user_messages:
                latest_user_message = user_messages[-1]["content"]
                
                # Log as metric and artifact
                mlflow.log_text(
                    latest_user_message, 
                    f"user_input_interaction_{interaction_num}.txt"
                )
                
                # Log message count and length as metrics
                mlflow.log_metrics({
                    f"user_message_length_interaction_{interaction_num}": len(latest_user_message),
                    f"total_messages_interaction_{interaction_num}": len(body["messages"]),
                    "total_interactions": interaction_num
                })
                
            self.log(f"User input logged for chat_id: {chat_id}, interaction: {interaction_num}")
            
        except Exception as e:
            self.log(f"Failed to log user input: {e}")

        return body

    async def outlet(self, body: dict, user: Optional[dict] = None) -> dict:
        self.log("MLflow Filter OUTLET called")

        # Check MLflow client status
        if not self.mlflow_client:
            self.log("[WARNING] MLflow client not initialized - Skipped")
            return body

        self.log(f"Outlet function called with body keys: {list(body.keys())}")

        chat_id = body.get("chat_id")

        # Handle temporary chats
        if chat_id == "local":
            session_id = body.get("session_id")
            chat_id = f"temporary-session-{session_id}"

        metadata = body.get("metadata", {})
        # Defaulting to 'llm_response' if no task is provided
        task_name = metadata.get("task", "llm_response")

        # Build tags
        tags_dict = self._build_tags(task_name)

        if chat_id not in self.chat_runs:
            self.log(f"[WARNING] No matching MLflow run found for chat_id: {chat_id}, attempting to re-register.")
            # Re-run inlet to register if somehow missing
            return await self.inlet(body, user)

        run_info = self.chat_runs[chat_id]
        assistant_message = get_last_assistant_message(body["messages"])
        assistant_message_obj = get_last_assistant_message_obj(body["messages"])

        # Extract usage information
        usage_metrics = {}
        if assistant_message_obj:
            info = assistant_message_obj.get("usage", {})
            if isinstance(info, dict):
                input_tokens = info.get("prompt_eval_count") or info.get("prompt_tokens")
                output_tokens = info.get("eval_count") or info.get("completion_tokens")
                
                if input_tokens is not None:
                    usage_metrics["input_tokens"] = input_tokens
                if output_tokens is not None:
                    usage_metrics["output_tokens"] = output_tokens
                if input_tokens is not None and output_tokens is not None:
                    usage_metrics["total_tokens"] = input_tokens + output_tokens
                    
                self.log(f"Usage metrics extracted: {usage_metrics}")

        # Get model information
        model_id = self.model_names.get(chat_id, {}).get("id", body.get("model"))
        model_name = self.model_names.get(chat_id, {}).get("name", "unknown")

        # Determine which model value to use based on valve setting
        model_value = (
            model_name
            if self.valves.use_model_name_instead_of_id
            else model_id
        )

        try:
            interaction_num = run_info["interaction_count"]
            
            # If not using separate runs, we need to set the active run
            if not self.valves.separate_runs_per_interaction:
                # Set the active run to continue logging to the chat run
                mlflow.start_run(run_id=run_info["run_id"])
            
            # Log assistant response
            if assistant_message:
                mlflow.log_text(
                    assistant_message,
                    f"assistant_response_interaction_{interaction_num}.txt"
                )
                
                # Log response metrics
                response_metrics = {
                    f"assistant_message_length_interaction_{interaction_num}": len(assistant_message),
                    f"response_time_interaction_{interaction_num}": time.time() - run_info.get("last_input_time", time.time())
                }
                
                # Add usage metrics if available
                if usage_metrics:
                    for key, value in usage_metrics.items():
                        response_metrics[f"{key}_interaction_{interaction_num}"] = value
                
                mlflow.log_metrics(response_metrics)
            
            # Log model information
            mlflow.log_params({
                f"model_used_interaction_{interaction_num}": model_value,
                "model_id": model_id,
                "model_name": model_name
            })
            
            # Log conversation history as artifact periodically
            if interaction_num % 5 == 0:  # Every 5 interactions
                conversation_history = json.dumps(body["messages"], indent=2)
                mlflow.log_text(
                    conversation_history,
                    f"conversation_history_interaction_{interaction_num}.json"
                )
            
            # Update run tags
            mlflow.set_tags({
                **tags_dict,
                "last_model_used": model_value,
                "total_interactions": str(interaction_num),
                "status": "active"
            })
            
            self.log(f"Assistant response logged for chat_id: {chat_id}, interaction: {interaction_num}")
            
            # End run if using separate runs per interaction
            if self.valves.separate_runs_per_interaction:
                mlflow.end_run()
            else:
                # Keep the run active but update timestamp
                run_info["last_response_time"] = time.time()
                
        except Exception as e:
            self.log(f"Failed to log assistant response: {e}")

        return body
