"""
title: Message Length Filter
author: David Weese
date: 2025-09-23
version: 1.0
license: MIT
description: Filter that enforces maximum input message length and caps/truncates assistant output length.
"""

from typing import List, Optional, Any
from pydantic import BaseModel
from schemas import OpenAIChatMessage
import os
import math


def _get_last_message_by_roles(messages: List[dict], roles: List[str]) -> Optional[dict]:
    for message in reversed(messages):
        if message.get("role") in roles:
            return message
    return None


def _compute_text_length(content: Any) -> int:
    # content can be a string or a list (multi-part). We count only textual segments.
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        total = 0
        for part in content:
            # Common OpenAI-style structured parts may include {type: "text", text: "..."}
            if isinstance(part, str):
                total += len(part)
            elif isinstance(part, dict):
                text = part.get("text") or part.get("content")
                if isinstance(text, str):
                    total += len(text)
        return total
    return 0


class Pipeline:
    class Valves(BaseModel):
        # Connect to these pipelines (models). Use ["*"] for all.
        pipelines: List[str] = ["*"]

        # Filter execution order among filters. Lower runs first.
        priority: int = 0

        # Input validation
        target_user_roles: List[str] = ["user"]
        max_user_message_chars: Optional[int] = int(os.getenv("MAX_USER_MESSAGE_CHARS", "20000"))

        # Output limits
        # If set, we will constrain generation length via tokens only
        max_assistant_response_tokens: Optional[int] = int(os.getenv("MAX_RESPONSE_TOKENS", "8192"))

    def __init__(self):
        # Pipeline filters are only compatible with Open WebUI
        self.type = "filter"
        self.name = "Message Length Filter"

        # Initialize valves with environment overrides where applicable
        self.valves = self.Valves(
            **{
                "pipelines": os.getenv("MSG_LEN_FILTER_PIPELINES", "*").split(","),
                # Other valves fall back to their defaults
            }
        )

    def _apply_output_token_cap(self, body: dict):
        # Enforce explicit token cap only
        desired_tokens = self.valves.max_assistant_response_tokens
        if desired_tokens is None:
            return

        options = body.get("options")
        if not isinstance(options, dict):
            options = {}
        options["max_tokens"] = min(options.get("max_tokens", desired_tokens), desired_tokens)
        body["options"] = options

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        # Validate input message length
        max_chars = self.valves.max_user_message_chars
        if max_chars and max_chars > 0:
            last_target_msg = _get_last_message_by_roles(body.get("messages", []), self.valves.target_user_roles)
            if last_target_msg:
                length = _compute_text_length(last_target_msg.get("content"))
                if length > max_chars:
                    raise Exception(
                        f"Your input message with {length} characters exceeds the limit of {max_chars} characters, please shorten your request."
                    )

        # Enforce output cap via tokens (top-level and options)
        self._apply_output_token_cap(body)
        return body
