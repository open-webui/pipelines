from typing import List, Union, Generator, Iterator
from pydantic import BaseModel
import requests
import os


class Pipeline:
    class Valves(BaseModel):
        # You can add your custom valves here.
        AZURE_DEEPSEEKR1_API_KEY: str
        AZURE_DEEPSEEKR1_ENDPOINT: str
        AZURE_DEEPSEEKR1_API_VERSION: str

    def __init__(self):
        self.type = "manifold"
        self.name = "Azure "
        self.valves = self.Valves(
            **{
                "AZURE_DEEPSEEKR1_API_KEY": os.getenv("AZURE_DEEPSEEKR1_API_KEY", "your-azure-deepseek-r1-api-key-here"),
                "AZURE_DEEPSEEKR1_ENDPOINT": os.getenv("AZURE_DEEPSEEKR1_ENDPOINT", "your-azure-deepseek-r1-endpoint-here"),
                "AZURE_DEEPSEEKR1_API_VERSION": os.getenv("AZURE_DEEPSEEKR1_API_VERSION", "2024-05-01-preview"),
            }
        )
        self.set_pipelines()
        pass

    def set_pipelines(self):
        models = ['DeepSeek-R1']
        model_names = ['DeepSeek-R1']
        self.pipelines = [
            {"id": model, "name": name} for model, name in zip(models, model_names)
        ]
        print(f"azure_deepseek_r1_pipeline - models: {self.pipelines}")
        pass

    async def on_valves_updated(self):
        self.set_pipelines()        

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
            "api-key": self.valves.AZURE_DEEPSEEKR1_API_KEY,
            "Content-Type": "application/json",
        }

        url = f"{self.valves.AZURE_DEEPSEEKR1_ENDPOINT}/models/chat/completions?api-version={self.valves.AZURE_DEEPSEEKR1_API_VERSION}"

        print(body)

        allowed_params = {'messages', 'temperature', 'role', 'content', 'contentPart', 'contentPartImage',
                          'enhancements', 'dataSources', 'n', 'stream', 'stop', 'max_tokens', 'presence_penalty',
                          'frequency_penalty', 'logit_bias', 'user', 'function_call', 'funcions', 'tools',
                          'tool_choice', 'top_p', 'log_probs', 'top_logprobs', 'response_format', 'seed', 'model'}
        # remap user field
        if "user" in body and not isinstance(body["user"], str):
            body["user"] = body["user"]["id"] if "id" in body["user"] else str(body["user"])
        # Fill in model field as per Azure's api requirements
        body["model"] = model_id
        filtered_body = {k: v for k, v in body.items() if k in allowed_params}
        # log fields that were filtered out as a single line
        if len(body) != len(filtered_body):
            print(f"Dropped params: {', '.join(set(body.keys()) - set(filtered_body.keys()))}")

        try:
            r = requests.post(
                url=url,
                json=filtered_body,
                headers=headers,
                stream=True,
            )

            r.raise_for_status()
            if body["stream"]:
                return r.iter_lines()
            else:
                return r.json()
        except Exception as e:
            if r:
                text = r.text
                return f"Error: {e} ({text})"
            else:
                return f"Error: {e}"
