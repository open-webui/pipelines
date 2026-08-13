"""
title: Langfuse v4 Filter Pipeline (hierarchical traces)
author: rahulbhooteshwar
date: 2026-08-13
version: 1.0.0
license: MIT
description: >
  Open WebUI filter pipeline for Langfuse Python SDK v4. Emits one trace per chat
  turn with a proper root observation (agent) and nested children
  (user prompt span, tool/retriever observations, LLM generation), instead of the
  flat, root-less traces produced by the v3 example pipeline.
requirements: langfuse>=4.7.0
"""

# NOTE: do NOT add `from __future__ import annotations` to this file. The Open WebUI
# pipelines server loads pipelines with importlib.util.module_from_spec() without
# registering them in sys.modules, so pydantic cannot resolve postponed (string)
# annotations and Valves fails to build with "`Valves` is not fully defined".

import json
import os
import threading
import time
import warnings
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel

from langfuse import Langfuse, propagate_attributes

try:  # Available when running inside the Open WebUI "pipelines" server.
    from utils.pipelines.main import get_last_assistant_message  # type: ignore
except Exception:  # pragma: no cover - exercised only outside the pipelines server

    def get_last_assistant_message(messages: List[dict]) -> str:
        for message in reversed(messages or []):
            if message.get("role") == "assistant":
                return _content_to_text(message.get("content"))
        return ""


# Open WebUI sets metadata["task"] for background calls such as title_generation,
# tags_generation, query_generation or autocomplete_generation. Those are real LLM
# calls but they are not part of the user-visible conversation, so they get their
# own trace rather than being folded into the chat turn. Anything without a task is
# the chat turn itself.
CHAT_TASK_NAME = "chat"

# Sampling/decoding parameters worth recording on the generation.
MODEL_PARAMETER_KEYS = (
    "temperature",
    "top_p",
    "top_k",
    "min_p",
    "max_tokens",
    "max_completion_tokens",
    "seed",
    "stop",
    "frequency_penalty",
    "presence_penalty",
    "repeat_penalty",
    "reasoning_effort",
    "stream",
)

MAX_PROPAGATED_VALUE_LENGTH = 200


def _content_to_text(content: Any) -> str:
    """Flatten Open WebUI message content (string or multi-part list) to text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    parts.append(part.get("text", ""))
                elif "text" in part:
                    parts.append(str(part["text"]))
            elif isinstance(part, str):
                parts.append(part)
        return "\n".join(p for p in parts if p)
    return str(content)


def get_last_assistant_message_obj(messages: List[dict]) -> dict:
    """Retrieve the last assistant message object from the message list."""
    for message in reversed(messages or []):
        if message.get("role") == "assistant":
            return message
    return {}


def get_last_user_message_obj(messages: List[dict]) -> dict:
    """Retrieve the last user message object from the message list."""
    for message in reversed(messages or []):
        if message.get("role") == "user":
            return message
    return {}


def _as_propagated_metadata(raw: Dict[str, Any]) -> Dict[str, str]:
    """Coerce metadata to the shape ``propagate_attributes`` accepts.

    v4 propagated metadata must be ``{str: str}`` with values <= 200 characters;
    anything else is dropped by the SDK with a warning.
    """
    propagated: Dict[str, str] = {}
    for key, value in raw.items():
        if value is None:
            continue
        text = value if isinstance(value, str) else json.dumps(value, default=str)
        if len(text) > MAX_PROPAGATED_VALUE_LENGTH:
            continue
        propagated[str(key)] = text
    return propagated


class Pipeline:
    class Valves(BaseModel):
        pipelines: List[str] = []
        priority: int = 0

        secret_key: str
        public_key: str
        host: str

        # Marks traces as dev/staging/prod inside Langfuse.
        environment: str = "default"
        release: str = ""

        # Adds "open-webui" and the task name as trace tags.
        insert_tags: bool = True
        # Use the human-readable model name rather than the model id on generations.
        use_model_name_instead_of_id_for_generation: bool = False
        # Which field of the Open WebUI user object becomes the Langfuse user id.
        user_id_field: str = "email"

        # Hierarchy toggles.
        capture_user_prompt_span: bool = True
        capture_tool_calls: bool = True
        capture_sources_as_retriever: bool = True
        # Log title/tag/query generation calls as their own traces.
        capture_task_traces: bool = True

        # Also write trace-level input/output. Needed for the trace list preview and
        # legacy LLM-as-a-judge evaluators on Langfuse servers that predate the
        # observations-first data model.
        set_trace_io: bool = True

        # Flush synchronously at the end of every outlet. Turn off for throughput.
        flush_on_outlet: bool = True

        # Safety net for turns that never reach outlet (cancelled/failed requests).
        open_turn_ttl_seconds: int = 1800
        max_open_turns: int = 2048

        debug: bool = False

    def __init__(self):
        self.type = "filter"
        self.name = "Langfuse Filter (v4)"

        self.valves = self.Valves(
            **{
                "pipelines": ["*"],
                "secret_key": os.getenv("LANGFUSE_SECRET_KEY", "your-secret-key-here"),
                "public_key": os.getenv("LANGFUSE_PUBLIC_KEY", "your-public-key-here"),
                "host": os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
                "environment": os.getenv("LANGFUSE_TRACING_ENVIRONMENT", "default"),
                "release": os.getenv("LANGFUSE_RELEASE", ""),
                "use_model_name_instead_of_id_for_generation": os.getenv(
                    "USE_MODEL_NAME", "false"
                ).lower()
                == "true",
                "debug": os.getenv("DEBUG_MODE", "false").lower() == "true",
            }
        )

        self.langfuse: Optional[Langfuse] = None
        # turn_key -> open turn state. Written by inlet, consumed by outlet.
        self._turns: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self._lock = threading.Lock()
        self.suppressed_logs = set()

    # ------------------------------------------------------------------ logging

    def log(self, message: str, suppress_repeats: bool = False):
        if self.valves.debug:
            if suppress_repeats:
                if message in self.suppressed_logs:
                    return
                self.suppressed_logs.add(message)
            print(f"[DEBUG] {message}")

    # ------------------------------------------------------------- lifecycle

    async def on_startup(self):
        self.log(f"on_startup triggered for {__name__}")
        self.set_langfuse()

    async def on_shutdown(self):
        self.log(f"on_shutdown triggered for {__name__}")
        with self._lock:
            open_turns = list(self._turns.items())
            self._turns.clear()
        for turn_key, turn in open_turns:
            self._abandon_turn(turn_key, turn, "pipeline shutdown before outlet")
        if self.langfuse:
            try:
                self.langfuse.shutdown()
                self.log("Langfuse client shut down and flushed")
            except Exception as e:
                self.log(f"Failed to shut down Langfuse client: {e}")

    async def on_valves_updated(self):
        self.log("Valves updated, resetting Langfuse client.")
        self.set_langfuse()

    def set_langfuse(self):
        # The v4 SDK caches its OTel resources per public key, so a plain re-init
        # would silently keep the old host/credentials. Tear the old one down first.
        if self.langfuse is not None:
            try:
                self.langfuse.shutdown()
            except Exception as e:
                self.log(f"Failed to shut down previous Langfuse client: {e}")
            try:
                from langfuse._client.resource_manager import LangfuseResourceManager

                LangfuseResourceManager.reset()
            except Exception as e:
                self.log(f"Could not reset cached Langfuse resources: {e}")
            self.langfuse = None

        try:
            self.log(f"Initializing Langfuse with host: {self.valves.host}")
            client = Langfuse(
                secret_key=self.valves.secret_key,
                public_key=self.valves.public_key,
                host=self.valves.host,
                environment=self.valves.environment or None,
                release=self.valves.release or None,
                debug=self.valves.debug,
            )
            client.auth_check()
            self.langfuse = client
            self.log(f"Langfuse client authenticated against {self.valves.host}")
        except Exception as e:
            self.log(f"Langfuse initialization/auth failed: {e}")
            self.langfuse = None

    # ------------------------------------------------------------ trace helpers

    def _build_tags(self, task_name: str) -> List[str]:
        tags_list: List[str] = []
        if self.valves.insert_tags:
            tags_list.append("open-webui")
            if task_name != CHAT_TASK_NAME:
                tags_list.append(task_name)
        return tags_list

    def _resolve_user_id(self, user: Optional[dict]) -> Optional[str]:
        if not user:
            return None
        preferred = self.valves.user_id_field or "email"
        for field in (preferred, "email", "id", "name"):
            value = user.get(field)
            if value:
                return str(value)
        return None

    @staticmethod
    def _turn_key(chat_id: str, message_id: Optional[str]) -> str:
        return f"{chat_id}:{message_id}" if message_id else chat_id

    @staticmethod
    def _resolve_chat_id(*containers: dict) -> str:
        """Resolve the chat id, mapping temporary chats onto their session.

        Open WebUI puts these fields under ``metadata`` on inlet but at the top
        level on outlet, so both are searched.
        """

        def first(key: str) -> Optional[str]:
            for container in containers:
                value = (container or {}).get(key)
                if value:
                    return str(value)
            return None

        chat_id = first("chat_id")
        if chat_id in (None, "", "local"):
            session_id = first("session_id")
            if session_id:
                return f"temporary-session-{session_id}"
            return "unknown-chat"
        return chat_id

    def _sweep_open_turns(self):
        """End turns that never reached outlet so their spans still get exported."""
        ttl = max(int(self.valves.open_turn_ttl_seconds), 0)
        max_open = max(int(self.valves.max_open_turns), 1)
        now = time.time()
        expired: List[Tuple[str, Dict[str, Any]]] = []

        with self._lock:
            if ttl > 0:
                for key, turn in list(self._turns.items()):
                    if now - turn["created_at"] > ttl:
                        expired.append((key, self._turns.pop(key)))
            while len(self._turns) > max_open:
                key, turn = self._turns.popitem(last=False)
                expired.append((key, turn))

        for key, turn in expired:
            self._abandon_turn(key, turn, "no outlet received before timeout")

    def _abandon_turn(self, turn_key: str, turn: Dict[str, Any], reason: str):
        """Close an orphaned turn so Langfuse still receives the observations."""
        try:
            generation = turn.get("generation")
            if generation is not None:
                generation.update(level="WARNING", status_message=reason)
                generation.end()
            root = turn.get("root")
            if root is not None:
                root.update(level="WARNING", status_message=reason)
                root.end()
            self.log(f"Closed abandoned turn {turn_key}: {reason}")
        except Exception as e:
            self.log(f"Failed to close abandoned turn {turn_key}: {e}")

    # --------------------------------------------------------------- extraction

    @staticmethod
    def _extract_model_parameters(body: dict) -> Dict[str, Any]:
        params = {}
        for key in MODEL_PARAMETER_KEYS:
            if key in body and body[key] is not None:
                value = body[key]
                params[key] = value if isinstance(value, (str, int, float, bool)) else json.dumps(value, default=str)
        options = body.get("options")
        if isinstance(options, dict):
            for key, value in options.items():
                if value is None or key in params:
                    continue
                params[key] = value if isinstance(value, (str, int, float, bool)) else json.dumps(value, default=str)
        return params

    @staticmethod
    def _extract_usage(assistant_message_obj: dict) -> Tuple[Optional[Dict[str, int]], Optional[Dict[str, float]]]:
        """Map Open WebUI / Ollama / OpenAI usage payloads to v4 usage_details."""
        info = assistant_message_obj.get("usage")
        if not isinstance(info, dict):
            nested = assistant_message_obj.get("info")
            info = nested if isinstance(nested, dict) else {}

        if not isinstance(info, dict) or not info:
            return None, None

        def first_int(*keys) -> Optional[int]:
            for key in keys:
                value = info.get(key)
                if isinstance(value, (int, float)):
                    return int(value)
            return None

        input_tokens = first_int("prompt_tokens", "prompt_eval_count", "input_tokens")
        output_tokens = first_int("completion_tokens", "eval_count", "output_tokens")
        total_tokens = first_int("total_tokens")

        usage_details: Dict[str, int] = {}
        if input_tokens is not None:
            usage_details["input"] = input_tokens
        if output_tokens is not None:
            usage_details["output"] = output_tokens
        if total_tokens is not None:
            usage_details["total"] = total_tokens
        elif input_tokens is not None and output_tokens is not None:
            usage_details["total"] = input_tokens + output_tokens

        prompt_details = info.get("prompt_tokens_details")
        if isinstance(prompt_details, dict):
            cached = prompt_details.get("cached_tokens")
            if isinstance(cached, (int, float)):
                usage_details["cache_read_input_tokens"] = int(cached)

        completion_details = info.get("completion_tokens_details")
        if isinstance(completion_details, dict):
            reasoning = completion_details.get("reasoning_tokens")
            if isinstance(reasoning, (int, float)):
                usage_details["reasoning_tokens"] = int(reasoning)

        cost_details: Dict[str, float] = {}
        for source_key, target_key in (
            ("cost", "total"),
            ("total_cost", "total"),
            ("input_cost", "input"),
            ("output_cost", "output"),
        ):
            value = info.get(source_key)
            if isinstance(value, (int, float)):
                cost_details[target_key] = float(value)

        return (usage_details or None), (cost_details or None)

    @staticmethod
    def _extract_completion_start_time(
        assistant_message_obj: dict, generation_started_at: Optional[float]
    ) -> Optional[datetime]:
        """Derive time-to-first-token from Ollama's nanosecond duration fields."""
        if generation_started_at is None:
            return None
        info = assistant_message_obj.get("usage")
        if not isinstance(info, dict):
            nested = assistant_message_obj.get("info")
            info = nested if isinstance(nested, dict) else {}
        if not isinstance(info, dict):
            return None

        prefill_ns = 0
        found = False
        for key in ("load_duration", "prompt_eval_duration"):
            value = info.get(key)
            if isinstance(value, (int, float)):
                prefill_ns += value
                found = True
        if not found:
            return None

        return datetime.fromtimestamp(generation_started_at + prefill_ns / 1e9, tz=timezone.utc)

    @staticmethod
    def _extract_tool_calls(messages: List[dict]) -> List[Dict[str, Any]]:
        """Reconstruct tool invocations from the message list of the current turn.

        Open WebUI hands the filter the finished conversation, so the tool calls and
        their results are recovered by pairing assistant ``tool_calls`` entries with
        the ``role: "tool"`` messages that answer them.
        """
        messages = messages or []
        # Only look at the tail of the conversation belonging to this turn.
        start = 0
        for index in range(len(messages) - 1, -1, -1):
            if messages[index].get("role") == "user":
                start = index + 1
                break
        turn_messages = messages[start:]

        results_by_id: Dict[str, dict] = {}
        for message in turn_messages:
            if message.get("role") == "tool":
                call_id = message.get("tool_call_id") or message.get("id")
                if call_id:
                    results_by_id[str(call_id)] = message

        tool_calls: List[Dict[str, Any]] = []
        for message in turn_messages:
            for call in message.get("tool_calls") or []:
                if not isinstance(call, dict):
                    continue
                function = call.get("function") or {}
                name = function.get("name") or call.get("name") or "tool"
                arguments = function.get("arguments")
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except (ValueError, TypeError):
                        pass
                call_id = str(call.get("id") or "")
                result = results_by_id.get(call_id, {})
                tool_calls.append(
                    {
                        "name": name,
                        "input": arguments,
                        "output": _content_to_text(result.get("content")) or None,
                        "metadata": {"tool_call_id": call_id} if call_id else {},
                    }
                )
        return tool_calls

    @staticmethod
    def _extract_sources(assistant_message_obj: dict) -> List[Dict[str, Any]]:
        """Extract Open WebUI citations (RAG / web search / tool sources)."""
        sources = assistant_message_obj.get("sources")
        if not isinstance(sources, list):
            return []

        extracted: List[Dict[str, Any]] = []
        for source in sources:
            if not isinstance(source, dict):
                continue
            descriptor = source.get("source")
            if isinstance(descriptor, dict):
                name = descriptor.get("name") or descriptor.get("id") or "source"
            else:
                name = str(descriptor or "source")
            extracted.append(
                {
                    "name": str(name),
                    "input": source.get("query") or source.get("metadata"),
                    "output": source.get("document"),
                    "metadata": {
                        k: v
                        for k, v in source.items()
                        if k not in ("document", "source", "query")
                    },
                }
            )
        return extracted

    # -------------------------------------------------------------------- inlet

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        self.log("Langfuse Filter INLET called")

        if not self.langfuse:
            self.log("[WARNING] Langfuse client not initialized - Skipped", suppress_repeats=True)
            return body

        missing_keys = [key for key in ("model", "messages") if key not in body]
        if missing_keys:
            raise ValueError(
                f"Error: Missing keys in the request body: {', '.join(missing_keys)}"
            )

        metadata = body.get("metadata") or {}
        chat_id = self._resolve_chat_id(metadata, body)
        metadata["chat_id"] = chat_id
        body["metadata"] = metadata

        message_id = metadata.get("message_id") or body.get("id")
        task_name = metadata.get("task") or CHAT_TASK_NAME

        is_task = task_name != CHAT_TASK_NAME
        if is_task and not self.valves.capture_task_traces:
            self.log(f"Skipping task trace for task '{task_name}'")
            return body

        model_info = metadata.get("model") if isinstance(metadata.get("model"), dict) else {}
        model_id = body.get("model")
        model_name = model_info.get("name") or model_id
        model_value = (
            model_name
            if self.valves.use_model_name_instead_of_id_for_generation
            else model_id
        )

        user_id = self._resolve_user_id(user)
        # Background tasks fire concurrently with the chat turn, so they need their
        # own trace id, otherwise they collide on the same key.
        trace_seed = f"open-webui:{chat_id}:{message_id or 'no-message-id'}:{task_name}"
        trace_id = Langfuse.create_trace_id(seed=trace_seed)

        propagated = {
            "user_id": user_id,
            "session_id": chat_id,
            "trace_name": f"open-webui:{task_name}",
            "tags": self._build_tags(task_name) or None,
            "metadata": _as_propagated_metadata(
                {
                    "interface": "open-webui",
                    "task": task_name,
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "model_id": model_id,
                    "model_name": model_name,
                }
            )
            or None,
        }
        propagated = {k: v for k, v in propagated.items() if v is not None}

        messages = body.get("messages") or []
        user_message_obj = get_last_user_message_obj(messages)
        user_prompt = _content_to_text(user_message_obj.get("content"))

        observation_metadata = {
            **{k: v for k, v in metadata.items() if k != "model"},
            "interface": "open-webui",
            "model_id": model_id,
            "model_name": model_name,
            "user_id": user_id,
        }

        try:
            with propagate_attributes(**propagated):
                # trace_context without a parent_span_id makes this span the ROOT
                # observation of the trace. This is the piece the v3 example pipeline
                # never exported, which is why Langfuse showed a flat trace.
                root = self.langfuse.start_observation(
                    trace_context={"trace_id": trace_id},
                    name=f"open-webui:{task_name}",
                    as_type="chain" if is_task else "agent",
                    input=user_prompt or messages,
                    metadata=observation_metadata,
                )

                if self.valves.set_trace_io:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", DeprecationWarning)
                        root.set_trace_io(input=user_prompt or messages)

                if self.valves.capture_user_prompt_span and not is_task:
                    prompt_span = root.start_observation(
                        name="user_prompt",
                        as_type="span",
                        input=user_prompt,
                        metadata={
                            "message_id": user_message_obj.get("id"),
                            "files": metadata.get("files"),
                            "tool_ids": metadata.get("tool_ids"),
                            "features": metadata.get("features"),
                        },
                    )
                    prompt_span.end()

                generation = root.start_observation(
                    name=f"llm:{model_value}" if model_value else "llm",
                    as_type="generation",
                    model=model_value,
                    input=messages,
                    model_parameters=self._extract_model_parameters(body) or None,
                    metadata={"model_id": model_id, "model_name": model_name},
                )
        except Exception as e:
            self.log(f"Failed to start trace for chat_id {chat_id}: {e}")
            return body

        turn_key = self._turn_key(chat_id, message_id)
        turn = {
            "trace_id": trace_id,
            "root": root,
            "generation": generation,
            "propagated": propagated,
            "created_at": time.time(),
            "generation_started_at": time.time(),
            "chat_id": chat_id,
            "task_name": task_name,
            "model_id": model_id,
            "model_name": model_name,
            "user_id": user_id,
            "messages": messages,
        }

        with self._lock:
            previous = self._turns.pop(turn_key, None)
            self._turns[turn_key] = turn
        if previous is not None:
            self._abandon_turn(turn_key, previous, "superseded by a newer request")

        # Sweep after inserting so the cap counts the turn that was just opened.
        self._sweep_open_turns()

        self.log(f"Started trace {trace_id} for turn {turn_key}")
        return body

    # ------------------------------------------------------------------- outlet

    async def outlet(self, body: dict, user: Optional[dict] = None) -> dict:
        self.log("Langfuse Filter OUTLET called")

        if not self.langfuse:
            self.log("[WARNING] Langfuse client not initialized - Skipped", suppress_repeats=True)
            return body

        metadata = body.get("metadata") or {}
        chat_id = self._resolve_chat_id(body, metadata)
        message_id = body.get("id") or metadata.get("message_id")
        turn_key = self._turn_key(chat_id, message_id)

        turn = self._pop_turn(chat_id, turn_key)
        if turn is None:
            # No inlet was seen (pipeline restarted mid-request, or the filter was
            # enabled between inlet and outlet). Nothing to attach to.
            self.log(f"[WARNING] No open turn found for {turn_key}; skipping outlet")
            return body

        messages = body.get("messages") or []
        assistant_message = get_last_assistant_message(messages)
        assistant_message_obj = get_last_assistant_message_obj(messages)

        usage_details, cost_details = self._extract_usage(assistant_message_obj)
        completion_start_time = self._extract_completion_start_time(
            assistant_message_obj, turn.get("generation_started_at")
        )

        error = assistant_message_obj.get("error") or body.get("error")
        level = "ERROR" if error else None
        status_message = None
        if error:
            status_message = error if isinstance(error, str) else json.dumps(error, default=str)

        root = turn["root"]
        generation = turn["generation"]

        try:
            generation.update(
                output=assistant_message,
                usage_details=usage_details,
                cost_details=cost_details,
                completion_start_time=completion_start_time,
                level=level,
                status_message=status_message,
            )
            generation.end()

            with propagate_attributes(**turn["propagated"]):
                if self.valves.capture_tool_calls:
                    for call in self._extract_tool_calls(messages):
                        tool_span = root.start_observation(
                            name=f"tool:{call['name']}",
                            as_type="tool",
                            input=call.get("input"),
                            output=call.get("output"),
                            metadata=call.get("metadata") or None,
                        )
                        tool_span.end()

                if self.valves.capture_sources_as_retriever:
                    for source in self._extract_sources(assistant_message_obj):
                        retriever_span = root.start_observation(
                            name=f"source:{source['name']}",
                            as_type="retriever",
                            input=source.get("input"),
                            output=source.get("output"),
                            metadata=source.get("metadata") or None,
                        )
                        retriever_span.end()

            root.update(
                output=assistant_message,
                level=level,
                status_message=status_message,
            )
            if self.valves.set_trace_io:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", DeprecationWarning)
                    root.set_trace_io(output=assistant_message)
            root.end()

            self.log(f"Completed trace {turn['trace_id']} for turn {turn_key}")
        except Exception as e:
            self.log(f"Failed to finalize trace for {turn_key}: {e}")

        if self.valves.flush_on_outlet:
            try:
                self.langfuse.flush()
            except Exception as e:
                self.log(f"Failed to flush Langfuse data: {e}")

        return body

    def _pop_turn(self, chat_id: str, turn_key: str) -> Optional[Dict[str, Any]]:
        """Find the open turn for this outlet, falling back to the newest in-chat turn."""
        with self._lock:
            turn = self._turns.pop(turn_key, None)
            if turn is not None:
                return turn
            for key in reversed(list(self._turns.keys())):
                candidate = self._turns[key]
                if candidate["chat_id"] == chat_id and candidate["task_name"] == CHAT_TASK_NAME:
                    return self._turns.pop(key)
        return None
