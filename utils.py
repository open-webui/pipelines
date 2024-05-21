import uuid
import time

from typing import List
from schemas import OpenAIChatMessage
from config import MODEL_ID


def stream_message_template(message: str):
    return {
        "id": f"rag-{str(uuid.uuid4())}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": MODEL_ID,
        "choices": [
            {
                "index": 0,
                "delta": {"content": message},
                "logprobs": None,
                "finish_reason": None,
            }
        ],
    }


def get_last_user_message(messages: List[OpenAIChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return None
