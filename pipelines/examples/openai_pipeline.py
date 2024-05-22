from typing import List, Union, Generator
from schemas import OpenAIChatMessage
import requests


class Pipeline:
    def __init__(self):
        pass

    async def on_startup(self):
        # This function is called when the server is started.
        print(f"on_startup:{__name__}")
        pass

    async def on_shutdown(self):
        # This function is called when the server is stopped.
        print(f"on_shutdown:{__name__}")
        pass

    def get_response(
        self, user_message: str, messages: List[OpenAIChatMessage], body: dict
    ) -> Union[str, Generator]:
        # This is where you can add your custom pipelines like RAG.'
        print(f"get_response:{__name__}")

        print(messages)
        print(user_message)
        OPENAI_API_KEY = "your-api-key-here"

        headers = {}
        headers["Authorization"] = f"Bearer {OPENAI_API_KEY}"
        headers["Content-Type"] = "application/json"

        r = requests.request(
            method="POST",
            url="https://api.openai.com/v1",
            data=body,
            headers=headers,
            stream=True,
        )

        r.raise_for_status()

        # Check if response is SSE
        if "text/event-stream" in r.headers.get("Content-Type", ""):
            return r.iter_content(chunk_size=8192)
        else:
            response_data = r.json()
            return f"{response_data['choices'][0]['text']}"
