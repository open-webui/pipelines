from typing import List, Union, Generator, Iterator
from schemas import OpenAIChatMessage
from pydantic import BaseModel
import os
import requests


class Pipeline:
    class Valves(BaseModel):
        CLOUDFLARE_ACCOUNT_ID: str = ""
        CLOUDFLARE_API_KEY: str = ""
        CLOUDFLARE_MODEL: str = ""
        pass

    def __init__(self):
        # Optionally, you can set the id and name of the pipeline.
        # Best practice is to not specify the id so that it can be automatically inferred from the filename, so that users can install multiple versions of the same pipeline.
        # The identifier must be unique across all pipelines.
        # The identifier must be an alphanumeric string that can include underscores or hyphens. It cannot contain spaces, special characters, slashes, or backslashes.
        # self.id = "openai_pipeline"
        self.name = "Cloudlfare AI"
        self.valves = self.Valves(
            **{
                "CLOUDFLARE_ACCOUNT_ID": os.getenv(
                    "CLOUDFLARE_ACCOUNT_ID",
                    "your-account-id",
                ),
                "CLOUDFLARE_API_KEY": os.getenv(
                    "CLOUDFLARE_API_KEY", "your-cloudflare-api-key"
                ),
                "CLOUDFLARE_MODEL": os.getenv(
                    "CLOUDFLARE_MODELS",
                    "@cf/meta/llama-3.1-8b-instruct",
                ),
            }
        )
        pass

    async def on_startup(self):
        # This function is called when the server is started.
        print(f"on_startup:{__name__}")
        pass

    async def on_shutdown(self):
        # This function is called when the server is stopped.
        print(f"on_shutdown:{__name__}")
        pass

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        # This is where you can add your custom pipelines like RAG.
        print(f"pipe:{__name__}")

        headers = {}
        headers["Authorization"] = f"Bearer {self.valves.CLOUDFLARE_API_KEY}"
        headers["Content-Type"] = "application/json"

        payload = {**body, "model": self.valves.CLOUDFLARE_MODEL}

        if "user" in payload:
            del payload["user"]
        if "chat_id" in payload:
            del payload["chat_id"]
        if "title" in payload:
            del payload["title"]

        try:
            r = requests.post(
                url=f"https://api.cloudflare.com/client/v4/accounts/{self.valves.CLOUDFLARE_ACCOUNT_ID}/ai/v1/chat/completions",
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
