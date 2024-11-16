from typing import List, Union, Generator, Iterator
from schemas import OpenAIChatMessage
from pydantic import BaseModel
import os
import requests
import json


class Pipeline:
    class Valves(BaseModel):
        XAI_API_KEY: str = ""
        pass

    def __init__(self):
        self.name = "X.AI Grok Pipeline"
        self.valves = self.Valves(
            **{
                "XAI_API_KEY": os.getenv(
                    "XAI_API_KEY", "your-xai-api-key-here"
                )
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

        XAI_API_KEY = self.valves.XAI_API_KEY
        MODEL = "grok-beta"

        headers = {}
        headers["Authorization"] = f"Bearer {XAI_API_KEY}"
        headers["Content-Type"] = "application/json"

        payload = {**body, "model": MODEL}

        # Remove unnecessary fields
        fields_to_remove = ["user", "chat_id", "title"]
        for field in fields_to_remove:
            if field in payload:
                del payload[field]

        print(payload)

        try:
            r = requests.post(
                url="https://api.x.ai/v1/chat/completions",
                json=payload,
                headers=headers,
                stream=True,
            )

            r.raise_for_status()

            if body.get("stream", False):
                return r.iter_lines()
            else:
                return r.json()
        except requests.exceptions.HTTPError as e:
            error_msg = {"error": str(e)}
            if e.response is not None:
                try:
                    error_msg = e.response.json()
                except:
                    pass
            return json.dumps({"error": error_msg})
        except Exception as e:
            return json.dumps({"error": str(e)})
