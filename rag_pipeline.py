from typing import List
from schemas import OpenAIChatMessage


def get_response(user_message: str, messages: List[OpenAIChatMessage]):
    print(messages)
    print(user_message)
    return f"rag response to: {user_message}"
