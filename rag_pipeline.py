from typing import List
from schemas import OpenAIChatMessage


def get_response(user_message: str, messages: List[OpenAIChatMessage]):
    # This is where you can add your custom RAG pipeline.
    # Typically, you would retrieve relevant information from your knowledge base and synthesize it to generate a response.

    print(messages)
    print(user_message)

    return f"rag response to: {user_message}"
