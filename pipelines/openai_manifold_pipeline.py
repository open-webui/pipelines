from typing import List, Union, Generator, Iterator
from schemas import OpenAIChatMessage
from pydantic import BaseModel
import requests


class Pipeline:
    def __init__(self):
        # This pipeline is set up as a manifold.
        self.type = "manifold"

        # Unique identifier and name for the pipeline.
        self.id = "openai_manifold"
        self.name = "OpenAI: "

        class Valves(BaseModel):
            OPENAI_BASE_URL: str
            OPENAI_API_KEY: str

        # Set your OpenAI API base URL and API key here.
        self.valves = Valves(**{
            "OPENAI_BASE_URL": "https://api.openai.com",
            "OPENAI_API_KEY": "[your-openai-api-key]",
        })
        self.pipelines = []

    async def on_startup(self):
        # Called when the server starts.
        print(f"on_startup:{__name__}")
        self.pipelines = self.get_openai_models()

    async def on_shutdown(self):
        # Called when the server stops.
        print(f"on_shutdown:{__name__}")

    async def on_valves_updated(self):
        # Called when the valves are updated.
        print(f"on_valves_updated:{__name__}")
        self.pipelines = self.get_openai_models()

    def get_openai_models(self):
        if self.valves.OPENAI_BASE_URL:
            try:
                headers = {"Authorization": f"Bearer {self.valves.OPENAI_API_KEY}"}
                response = requests.get(
                    f"{self.valves.OPENAI_BASE_URL}/v1/models",
                    headers=headers
                )
                response.raise_for_status()
                models_data = response.json()
                # OpenAI returns models in the "data" field.
                models = [
                    {"id": model["id"], "name": model["id"]}
                    for model in models_data.get("data", [])
                ]
                # Append your custom model.

                return models
            except Exception as e:
                print(f"Error: {e}")
                return [
                    {
                        "id": self.id,
                        "name": "Could not fetch models from OpenAI. Please check your API key and URL.",
                    },
                ]
        else:
            return []




    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        # Log user information if provided.
        if "user" in body:
            print("######################################")
            print(f'# User: {body["user"]["name"]} ({body["user"]["id"]})')
            print(f"# Message: {user_message}")
            print("######################################")

        # Ensure the required 'messages' field is present.
        if "messages" not in body:
            body["messages"] = messages

        # Build the payload using everything from 'body' and override/ensure
        # the required keys ('model' and 'messages') are correctly set.
        payload = {**body, "model": model_id, "messages": body.get("messages", messages)}

        # Remove keys that are not allowed by the OpenAI API.
        # For OpenAI, we omit the 'user' key completely (unless you want to include one.. webui sends a dict, which doesn't work with this API).
        payload.pop("user", None)

        # Debug: print the payload to verify its structure.
        print("Payload:", payload)

        try:
            headers = {"Authorization": f"Bearer {self.valves.OPENAI_API_KEY}"}
            response = requests.post(
                url=f"{self.valves.OPENAI_BASE_URL}/v1/chat/completions",
                json=payload,
                headers=headers,
                stream=payload.get("stream", False)
            )
            response.raise_for_status()

            if payload.get("stream", False):
                return response.iter_lines()
            else:
                return response.json()
        except Exception as e:
            return f"Error: {e}"
