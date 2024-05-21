from typing import List, Union, Generator
from schemas import OpenAIChatMessage


def get_response(
    user_message: str, messages: List[OpenAIChatMessage]
) -> Union[str, Generator]:
    # This is where you can add your custom pipelines like RAG.

    print(messages)
    print(user_message)

    return f"rag response to: {user_message}"
