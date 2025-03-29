from typing import List, Union, Generator, Iterator
from pydantic import BaseModel
import os
import requests

from utils.pipelines.main import pop_system_message


class Pipeline:
    class Valves(BaseModel):
        PERPLEXITY_API_BASE_URL: str = "https://api.perplexity.ai"
        PERPLEXITY_API_KEY: str = ""
        pass

    def __init__(self):
        self.type = "manifold"
        self.name = "Perplexity: "

        self.valves = self.Valves(
            **{
                "PERPLEXITY_API_KEY": os.getenv(
                    "PERPLEXITY_API_KEY", "your-perplexity-api-key-here"
                )
            }
        )

        # Debugging: print the API key to ensure it's loaded
        print(f"Loaded API Key: {self.valves.PERPLEXITY_API_KEY}")

        # List of models
        self.pipelines = [
            {
                "id": "sonar-pro",
                "name": "Sonar Pro"
            },
            {
                "id": "sonar",
                "name": "Sonar"
            },
            {
                "id": "sonar-deep-research",
                "name": "Sonar Deep Research"
            },
            {
                "id": "sonar-reasoning-pro",
                "name": "Sonar Reasoning Pro"
            },
            {
                "id": "sonar-reasoning", "name": "Sonar Reasoning"
            },
            {
                "id": "r1-1776", "name": "R1-1776"
            }
        ]
        pass

    async def on_startup(self):
        # This function is called when the server is started.
        print(f"on_startup:{__name__}")
        pass

    async def on_shutdown(self):
        # This function is called when the server is stopped.
        print(f"on_shutdown:{__name__}")
        pass

    async def on_valves_updated(self):
        # This function is called when the valves are updated.
        print(f"on_valves_updated:{__name__}")
        # No models to fetch, static setup
        pass

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        # This is where you can add your custom pipelines like RAG.
        print(f"pipe:{__name__}")

        system_message, messages = pop_system_message(messages)
        system_prompt = "You are a helpful assistant."
        if system_message is not None:
            system_prompt = system_message["content"]

        print(system_prompt)
        print(messages)
        print(user_message)

        headers = {
            "Authorization": f"Bearer {self.valves.PERPLEXITY_API_KEY}",
            "Content-Type": "application/json",
            "accept": "application/json"
        }

        payload = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                *messages
            ],
            "stream": body.get("stream", True),
            "return_citations": True,
            "return_images": True
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
                url=f"{self.valves.PERPLEXITY_API_BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
                stream=True,
            )

            r.raise_for_status()

            if body.get("stream", False):
                return r.iter_lines()
            else:
                response = r.json()
                formatted_response = {
                    "id": response["id"],
                    "model": response["model"],
                    "created": response["created"],
                    "usage": response["usage"],
                    "object": response["object"],
                    "choices": [
                        {
                            "index": choice["index"],
                            "finish_reason": choice["finish_reason"],
                            "message": {
                                "role": choice["message"]["role"],
                                "content": choice["message"]["content"]
                            },
                            "delta": {"role": "assistant", "content": ""}
                        } for choice in response["choices"]
                    ]
                }
                return formatted_response
        except Exception as e:
            return f"Error: {e}"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Perplexity API Client")
    parser.add_argument("--api-key", type=str, required=True,
                        help="API key for Perplexity")
    parser.add_argument("--prompt", type=str, required=True,
                        help="Prompt to send to the Perplexity API")

    args = parser.parse_args()

    pipeline = Pipeline()
    pipeline.valves.PERPLEXITY_API_KEY = args.api_key
    response = pipeline.pipe(
        user_message=args.prompt, model_id="llama-3-sonar-large-32k-online", messages=[], body={"stream": False})

    print("Response:", response)
