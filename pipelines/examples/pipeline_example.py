from typing import List, Union, Generator
from schemas import OpenAIChatMessage


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
    ) -> Union[str, Generator, Iterator]:
        # This is where you can add your custom pipelines like RAG.'
        print(f"get_response:{__name__}")

        print(messages)
        print(user_message)
        print(body)

        return f"{__name__} response to: {user_message}"
