import os
from typing import Generator, Iterator, List, Union

import requests
from pydantic import BaseModel


class Pipeline:
    class Valves(BaseModel):
        CLOUDFLARE_ACCOUNT_ID: str = ""
        CLOUDFLARE_API_KEY: str = ""
        pass

    def __init__(self):
        self.type = "manifold"
        self.name = "Cloudflare/"
        self.id = "cloudflare"
        self.valves = self.Valves(
            **{
                "CLOUDFLARE_ACCOUNT_ID": os.getenv(
                    "CLOUDFLARE_ACCOUNT_ID",
                    "your-account-id",
                ),
                "CLOUDFLARE_API_KEY": os.getenv(
                    "CLOUDFLARE_API_KEY", "your-cloudflare-api-key"
                ),
            }
        )
        self.pipelines = []
        self.update_headers()
        self.get_models()

    def update_headers(self):
        self.headers = {
            "Authorization": f"Bearer {self.valves.CLOUDFLARE_API_KEY}",
            "content-type": "application/json",
        }

    def get_models(self):
        if self.valves.CLOUDFLARE_ACCOUNT_ID and self.valves.CLOUDFLARE_API_KEY:
            try:
                list_models = requests.get(
                    f"https://api.cloudflare.com/client/v4/accounts/{self.valves.CLOUDFLARE_ACCOUNT_ID}/ai/models/search?task=Text%20Generation",
                    headers=self.headers,
                ).json()

                models = list_models["result"]
                self.pipelines = [
                    {
                        "id": model["name"].replace("/", "___"),
                        "name": model["name"].replace("/", "___").split("___")[-1],
                    }
                    for model in models
                ]
            except Exception as e:
                print(f"Error: {e}")
                self.pipelines = [
                    {
                        "id": self.id,
                        "name": "Could not fetch models from Cloudflare, please update the API Key in the valves.",
                    },
                ]
        else:
            self.pipelines = []

    async def on_startup(self):
        # This function is called when the server is started.
        print(f"on_startup:{__name__}")
        self.update_headers()
        self.get_models()
        pass

    async def on_shutdown(self):
        # This function is called when the server is stopped.
        print(f"on_shutdown:{__name__}")
        pass

    async def on_valves_updated(self):
        self.update_headers()
        self.get_models()

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        # This is where you can add your custom pipelines like RAG.
        print(f"pipe:{__name__}")

        # fix model name again, url messed up otherwise
        model = model_id.replace("___", "/")

        payload = {**body, "model": model}

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
                headers=self.headers,
                stream=True,
            )

            r.raise_for_status()

            if body["stream"]:
                return r.iter_lines()
            else:
                return r.json()
        except Exception as e:
            return f"Error: {e}"
