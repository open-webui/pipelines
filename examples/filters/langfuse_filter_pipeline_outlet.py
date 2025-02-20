"""
title: Langfuse Filter Pipeline Outlet
author: open-webui
date: 2025-02-19
version: 1.4
license: MIT
description: A filter pipeline that uses Langfuse.
requirements: langfuse
"""

from typing import List, Optional
import os
import uuid

from utils.pipelines.main import get_last_assistant_message
from pydantic import BaseModel
from langfuse import Langfuse
from langfuse.api.resources.commons.errors.unauthorized_error import UnauthorizedError


def get_last_assistant_message_obj(messages: List[dict]) -> dict:
    for message in reversed(messages):
        if message["role"] == "assistant":
            return message
    return {}


def remove_last_assistant_message(messages: List[dict]) -> List[dict]:
    if messages and messages[-1]["role"] == "assistant":
        return messages[:-1]
    return messages


class Pipeline:
    class Valves(BaseModel):
        pipelines: List[str] = []
        priority: int = 0
        secret_key: str
        public_key: str
        host: str

    def __init__(self):
        self.type = "filter"
        self.name = "Langfuse Filter Outlet"
        self.valves = self.Valves(
            **{
                "pipelines": ["*"],
                "secret_key": os.getenv("LANGFUSE_SECRET_KEY", "your-secret-key-here"),
                "public_key": os.getenv("LANGFUSE_PUBLIC_KEY", "your-public-key-here"),
                "host": os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
            }
        )
        self.langfuse = None

    async def on_startup(self):
        print(f"on_startup:{__name__}")
        self.set_langfuse()

    async def on_shutdown(self):
        print(f"on_shutdown:{__name__}")
        self.langfuse.flush()

    async def on_valves_updated(self):
        self.set_langfuse()

    def set_langfuse(self):
        try:
            self.langfuse = Langfuse(
                secret_key=self.valves.secret_key,
                public_key=self.valves.public_key,
                host=self.valves.host,
                debug=False,
            )
            self.langfuse.auth_check()
        except UnauthorizedError:
            print(
                "Langfuse credentials incorrect. Please re-enter your Langfuse credentials in the pipeline settings."
            )
        except Exception as e:
            print(
                f"Langfuse error: {e} Please re-enter your Langfuse credentials in the pipeline settings."
            )

    async def outlet(self, body: dict, user: Optional[dict] = None) -> dict:
        print(f"outlet:{__name__}")
        print(f"Received body: {body}")

        if "chat_id" not in body:
            print("chat_id not in body")
            return body

        user_id = user.get("id") if user else None
        user_name = user.get("name") if user else None
        user_email = user.get("email") if user else None

        input_messages = remove_last_assistant_message(body["messages"])
        trace = self.langfuse.trace(
            name=f"filter:{__name__}",
            input=input_messages,
            user_id=user_email,
            metadata={
                "user_name": user_name,
                "user_id": user_id,
                "chat_id": body["chat_id"],
            },
            session_id=body["chat_id"],
        )

        generation = trace.generation(
            name=body["chat_id"],
            model=body["model"],
            input=input_messages,
            metadata={"interface": "open-webui"},
        )

        assistant_message = get_last_assistant_message(body["messages"])

        # Extract usage information for models that support it
        usage = None
        assistant_message_obj = get_last_assistant_message_obj(body["messages"])
        if assistant_message_obj:
            info = assistant_message_obj.get("info", {})
            if isinstance(info, dict):
                input_tokens = info.get("prompt_eval_count") or info.get(
                    "prompt_tokens"
                )
                output_tokens = info.get("eval_count") or info.get("completion_tokens")
                if input_tokens is not None and output_tokens is not None:
                    usage = {
                        "input": input_tokens,
                        "output": output_tokens,
                        "unit": "TOKENS",
                    }

        # Update generation
        trace.update(
            output=assistant_message,
        )
        generation.end(
            output=assistant_message,
            metadata={"interface": "open-webui"},
            usage=usage,
        )

        return body
