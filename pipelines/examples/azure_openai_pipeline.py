from typing import List, Union, Generator, Iterator
from schemas import OpenAIChatMessage
import requests


class Pipeline:
    def __init__(self):
        # Optionally, you can set the id and name of the pipeline.
        self.id = "azure_openai_pipeline"
        self.name = "Azure OpenAI Pipeline"
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

        AZURE_OPENAI_API_KEY = "your-azure-openai-api-key-here"
        AZURE_OPENAI_ENDPOINT = "your-azure-openai-endpoint-here"
        DEPLOYMENT_NAME = "your-deployment-name-here"
        MODEL = "gpt-3.5-turbo"

        headers = {"api-key": AZURE_OPENAI_API_KEY, "Content-Type": "application/json"}

        url = f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{DEPLOYMENT_NAME}/chat/completions?api-version=2023-10-01-preview"

        try:
            r = requests.post(
                url=url,
                json={**body, "model": MODEL},
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
