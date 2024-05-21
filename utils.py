import uuid
import time
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
