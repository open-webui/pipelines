import uuid
import time

from typing import List
from schemas import OpenAIChatMessage


def stream_message_template(model: str, message: str):
    return {
        "id": f"{model}-{str(uuid.uuid4())}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"content": message},
                "logprobs": None,
                "finish_reason": None,
            }
        ],
    }


def get_last_user_message(messages: List[dict]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return None
