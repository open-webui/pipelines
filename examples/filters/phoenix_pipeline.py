"""
title: Phoenix Filter Pipeline
author:  Frank Deng <dengjia@gmail.com>
date: 2025-09-09
version: 1.0
license: MIT
description: A pipeline for Phoenix integration
requirements: arize-phoenix-otel
"""

import logging
import json
import os
from collections.abc import Iterator
from typing import Any


from pydantic import BaseModel
import phoenix.otel
from openinference.instrumentation import using_attributes, OITracer
from openinference.semconv.trace import (
    MessageAttributes,
    OpenInferenceMimeTypeValues,
    OpenInferenceSpanKindValues,
    SpanAttributes,
)
from opentelemetry.trace import use_span, Span

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def _llm_span_kind_attributes() -> Iterator[tuple[str, str]]:
    """
    Yields the OpenInference span kind attribute for LLMs.
    """
    yield SpanAttributes.OPENINFERENCE_SPAN_KIND, OpenInferenceSpanKindValues.LLM.value


def _llm_model_name_attributes(model_name: str) -> Iterator[tuple[str, str]]:
    """
    Yields the OpenInference model name attribute.
    """
    yield SpanAttributes.LLM_MODEL_NAME, model_name


def _input_attributes(payload: Any) -> Iterator[tuple[str, str]]:
    """
    Yields the OpenInference input value attribute as a JSON string if the
    payload can be serialized as JSON, otherwise as a string.
    """
    try:
        yield SpanAttributes.INPUT_VALUE, json.dumps(payload)
        yield SpanAttributes.INPUT_MIME_TYPE, OpenInferenceMimeTypeValues.JSON.value
    except json.JSONDecodeError:
        yield SpanAttributes.INPUT_VALUE, str(payload)
        yield SpanAttributes.INPUT_MIME_TYPE, OpenInferenceMimeTypeValues.TEXT.value


def _llm_input_messages_attributes(
    messages: list[dict[str, Any]],
) -> Iterator[tuple[str, str]]:
    """
    Yields the OpenInference input messages attributes for each message in the list.
    """
    for messages_index, message in enumerate(messages):
        yield (
            f"{SpanAttributes.LLM_INPUT_MESSAGES}.{messages_index}."
            f"{MessageAttributes.MESSAGE_ROLE}",
            message.get("role", ""),
        )
        yield (
            f"{SpanAttributes.LLM_INPUT_MESSAGES}.{messages_index}."
            f"{MessageAttributes.MESSAGE_CONTENT}",
            message.get("content", ""),
        )


def _metadata_attributes(metadata: dict[str, Any]) -> Iterator[tuple[str, str]]:
    """
    Yields the OpenInference metadata attributes.
    """

    def flatten(prefix: str, value: Any) -> Iterator[tuple[str, str]]:
        if isinstance(value, dict):
            for k, v in value.items():
                yield from flatten(f"{prefix}.{k}", v)
        elif isinstance(value, list):
            for i, v in enumerate(value):
                yield from flatten(f"{prefix}.{i}", v)
        else:
            yield prefix, str(value)

    for key, value in metadata.items():
        yield from flatten(f"{SpanAttributes.METADATA}.{key}", value)


def _output_attributes(payload: Any) -> Iterator[tuple[str, str]]:
    """
    Yields the OpenInference output value attribute as a JSON string if the
    payload can be serialized as JSON, otherwise as a string.
    """
    try:
        yield SpanAttributes.OUTPUT_VALUE, json.dumps(payload)
        yield SpanAttributes.OUTPUT_MIME_TYPE, OpenInferenceMimeTypeValues.JSON.value
    except TypeError:
        yield SpanAttributes.OUTPUT_VALUE, str(payload)
        yield SpanAttributes.OUTPUT_MIME_TYPE, OpenInferenceMimeTypeValues.TEXT.value


def _llm_output_message_attributes(
    message: dict[str, Any]
) -> Iterator[tuple[str, str]]:
    """
    Yields the OpenInference output message attributes.
    """
    yield (
        f"{SpanAttributes.LLM_OUTPUT_MESSAGES}.0.{MessageAttributes.MESSAGE_ROLE}",
        message.get("role", ""),
    )
    yield (
        f"{SpanAttributes.LLM_OUTPUT_MESSAGES}.0.{MessageAttributes.MESSAGE_CONTENT}",
        message.get("content", ""),
    )


# pylint: disable=too-few-public-methods,disable=missing-function-docstring
class Pipeline:
    """A filter pipeline for Phoenix integration."""

    class Valves(BaseModel):
        """Valve settings for the Phoenix filter pipeline."""

        # List target pipeline ids (models) that this filter will be connected to.
        # If you want to connect this filter to all pipelines, you can set pipelines to ["*"]
        # e.g. ["llama3:latest", "gpt-3.5-turbo"]
        pipelines: list[str] = []

        # Assign a priority level to the filter pipeline.
        # The priority level determines the order in which the filter pipelines are executed.
        # The lower the number, the higher the priority.
        priority: int = 0

        # Add your custom parameters here
        debug: bool = False

    def __init__(self) -> None:
        # Pipeline filters are only compatible with Open WebUI
        # You can think of filter pipeline as a middleware that can be used to
        # edit the form data before it is sent to the OpenAI API.
        self.type = "filter"

        # Optionally, you can set the id and name of the pipeline.
        # Best practice is to not specify the id so that it can be automatically
        # inferred from the filename, so that users can install multiple versions
        # of the same pipeline.
        # The identifier must be unique across all pipelines.
        # The identifier must be an alphanumeric string that can include underscores or hyphens.
        # It cannot contain spaces, special characters, slashes, or backslashes.
        # self.id = "phoenix_filter_pipeline"
        self.name = "Phoenix Filter"

        # Initialize
        self.valves = self.Valves(
            pipelines=["*"],  # Connect to all pipelines
            priority=0,
            debug=False,
        )

        self._debug = self.valves.debug

        self._tracer: OITracer | None = None

        self._spans: dict[str, dict[str, Span]] = {
            "response_generation": {},
            "follow_up_generation": {},
            "title_generation": {},
            "tags_generation": {},
        }

    async def on_startup(self) -> None:
        # This function is called when the server is started.
        logger.info("on_startup: %s, valves: %s", __name__, self.valves)
        self._set_tracer()

    async def on_shutdown(self) -> None:
        # This function is called when the server is stopped.
        logger.info("on_shutdown: %s", __name__)
        try:
            for spans in self._spans.values():
                for span in spans.values():
                    span.end()
        except Exception as e:  # pylint: disable=broad-except
            logger.error("Error occurred during shutdown: %s", e)

    async def on_valves_updated(self) -> None:
        # This function is called when the valves are updated.
        logger.info("on_valves_updated: %s, valves: %s", __name__, self.valves)
        self._debug = self.valves.debug

    # pylint: disable=too-many-locals
    async def inlet(
        self, body: dict[str, Any], user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        # This filter is applied to the form data before it is sent to the OpenAI API.
        if self._tracer is None:
            logger.warning("tracer is not initialized")
            return body

        if self._debug:
            logger.info(
                "%s inlet function called with body: %s and user: %s",
                __name__,
                body,
                user,
            )

        required_keys = ["model", "messages", "metadata"]
        missing_keys = [key for key in required_keys if key not in body]
        if missing_keys:
            error_message = f"Error: Missing keys in the request body: {missing_keys}"
            raise ValueError(error_message)

        metadata = body.get("metadata")
        if metadata is None:
            raise ValueError("Error: Missing metadata in the request body")

        message_id = metadata.get("message_id")
        if message_id is None:
            raise ValueError("Error: Missing message_id in metadata")

        chat_id = metadata.get("chat_id")
        # Handle temporary chats
        if chat_id is None or chat_id == "local":
            session_id = metadata.get("session_id")
            chat_id = f"temporary-session-{session_id}"
            metadata["chat_id"] = chat_id
            body["metadata"] = metadata

        # task type
        task = metadata.get("task", "response_generation")

        # model
        model_info = metadata.get("model", {})
        model_id = body.get("model", model_info.get("id", "unknown"))

        messages = body.get("messages", [])

        # Inject system message from metadata if present, avoid duplicates
        if task == "response_generation":
            system_content = model_info.get("info", {}).get("params", {}).get("system")
            if system_content:
                # Remove all existing system messages
                messages = [m for m in messages if m.get("role") != "system"]
                system_message = {
                    "role": "system",
                    "content": system_content,
                }
                messages = [system_message] + messages

        openai_payload = {
            "model": model_id,
            "messages": messages,
        }

        # TODO: follow_up_generation, title_generation, tags_generation tasks
        # are missing outlet, so we end the span here for now
        end_on_exit = task != "response_generation"

        with using_attributes(
            session_id=chat_id,
            user_id=user.get("name", "unknown") if user else "unknown",
        ):

            if message_id in self._spans[task]:
                span = self._spans[task][message_id]
            else:
                span = self._tracer.start_span(name=task)
                self._spans[task][message_id] = span

            with use_span(span, end_on_exit=end_on_exit):
                for attribute_key, attribute_value in (
                    *_metadata_attributes(metadata),
                    *_input_attributes(openai_payload),
                    *_llm_span_kind_attributes(),
                    *_llm_model_name_attributes(model_id),
                    *_llm_input_messages_attributes(messages),
                ):
                    span.set_attribute(attribute_key, attribute_value)

        if end_on_exit:
            self._spans[task].pop(message_id, None)

        return body

    # pylint: disable=too-many-locals
    async def outlet(
        self, body: dict[str, Any], user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if self._tracer is None:
            logger.warning("tracer is not initialized")
            return body

        if self._debug:
            logger.info(
                "%s outlet function called with body: %s and user: %s",
                __name__,
                body,
                user,
            )

        required_keys = ["messages", "id"]
        missing_keys = [key for key in required_keys if key not in body]
        if missing_keys:
            error_message = f"Error: Missing keys in the response body: {missing_keys}"
            raise ValueError(error_message)

        message_id = body.get("id")
        if message_id is None:
            raise ValueError("Error: Missing id in the response body")

        chat_id = body.get("chat_id")
        # Handle temporary chats
        if chat_id is None or chat_id == "local":
            session_id = body.get("session_id")
            chat_id = f"temporary-session-{session_id}"
            body["chat_id"] = chat_id

        messages = body.get("messages")
        _assistant_message = messages[-1] if messages else {}
        if _assistant_message and _assistant_message.get("role") == "assistant":
            assistant_message = {
                "role": "assistant",
                "content": _assistant_message.get("content"),
            }
        else:
            assistant_message = {
                "role": "assistant",
                "content": "",
            }

        # task type
        task = body.get("task", "response_generation")

        with using_attributes(
            session_id=chat_id,
            user_id=user.get("name", "unknown") if user else "unknown",
        ):

            if message_id in self._spans[task]:
                span = self._spans[task][message_id]
            else:
                span = self._tracer.start_span(name=task)
                self._spans[task][message_id] = span

            with use_span(span, end_on_exit=True):
                for attribute_key, attribute_value in (
                    *_llm_span_kind_attributes(),
                    *_output_attributes(body),
                    *_llm_output_message_attributes(assistant_message),
                ):
                    span.set_attribute(attribute_key, attribute_value)

        self._spans[task].pop(message_id, None)

        return body

    def _set_tracer(self) -> None:

        tracer_provider = phoenix.otel.register(
            project_name=os.getenv("PHOENIX_PROJECT_NAME", "open-webui-pipelines"),
            endpoint=os.getenv(
                "PHOENIX_ENDPOINT",
                "http://phoenix.phoenix.svc.cluster.local/v1/traces",
            ),
            auto_instrument=True,
            set_global_tracer_provider=False,
            batch=True,
        )

        self._tracer = tracer_provider.get_tracer(__name__)
