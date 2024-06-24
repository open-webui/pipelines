from typing import List, Union, Generator, Iterator
from schemas import OpenAIChatMessage
from pydantic import BaseModel
import os
import requests

class Pipeline:
    class Valves(BaseModel):
        INFOMANIAK_API_KEY: str = ""
        PRODUCT_ID: int = 0
        MODEL: str = ""

    def __init__(self):
        self.name = "Infomaniak"
        self.valves = self.Valves(
            **{
                "INFOMANIAK_API_KEY": os.getenv("INFOMANIAK_API_KEY", "infomaniak api key here"),                
                "PRODUCT_ID": int(os.getenv("PRODUCT_ID", 0)),
                "MODEL": os.getenv("MODEL", "mixtral, mixtral8x22b or llama3"),
            }
        )
        pass

    async def on_startup(self):
        print(f"on_startup:{__name__}")
        pass

    async def on_shutdown(self):
        print(f"on_shutdown:{__name__}")
        pass

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        print(f"pipe:{__name__}")

        print(messages)
        print(user_message)

        INFOMANIAK_API_KEY = self.valves.INFOMANIAK_API_KEY
        MODEL = self.valves.MODEL
        PRODUCT_ID = self.valves.PRODUCT_ID

        headers = {}
        headers["Authorization"] = f"Bearer {INFOMANIAK_API_KEY}"
        headers["Content-Type"] = "application/json"

        payload = {
            **body,
            "model": MODEL,
            "messages": messages
        }

        if "user" in payload:
            del payload["user"]
        if "chat_id" in payload:
            del payload["chat_id"]
        if "title" in payload:
            del payload["title"]

        print(payload)

        try:
            r = requests.post(
                url=f"https://api.infomaniak.com/1/ai/{PRODUCT_ID}/openai/chat/completions",
                json=payload,
                headers=headers,
                stream=True,
            )

            r.raise_for_status()

            if body["stream"]:
                return r.iter_lines()
            else:
                return r.json()
        except Exception as e:
            return f"Error: {e}"
