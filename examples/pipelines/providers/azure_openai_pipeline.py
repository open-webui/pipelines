from typing import List, Union, Generator, Iterator
from schemas import OpenAIChatMessage
from pydantic import BaseModel
import requests


class Pipeline:
    class Valves(BaseModel):
        # You can add your custom valves here.
        AZURE_OPENAI_API_KEY: str = "your-azure-openai-api-key-here"
        AZURE_OPENAI_ENDPOINT: str = "your-azure-openai-endpoint-here"
        DEPLOYMENT_NAME: str = "your-deployment-name-here"
        API_VERSION: str = "2023-10-01-preview"
        MODEL: str = "gpt-3.5-turbo"
        pass

    def __init__(self):
        # Optionally, you can set the id and name of the pipeline.
        # Best practice is to not specify the id so that it can be automatically inferred from the filename, so that users can install multiple versions of the same pipeline.
        # The identifier must be unique across all pipelines.
        # The identifier must be an alphanumeric string that can include underscores or hyphens. It cannot contain spaces, special characters, slashes, or backslashes.
        # self.id = "azure_openai_pipeline"
        self.name = "Azure OpenAI Pipeline"
        self.valves = self.Valves()
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

        print(messages)
        print(user_message)

        headers = {
            "api-key": self.valves.AZURE_OPENAI_API_KEY,
            "Content-Type": "application/json",
        }

        url = f"{self.valves.AZURE_OPENAI_ENDPOINT}/openai/deployments/{self.valves.DEPLOYMENT_NAME}/chat/completions?api-version={self.valves.API_VERSION}"

        try:
            r = requests.post(
                url=url,
                json={**body, "model": self.valves.MODEL},
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
