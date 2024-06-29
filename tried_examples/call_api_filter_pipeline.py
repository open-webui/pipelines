from typing import List, Optional
from schemas import OpenAIChatMessage
from pydantic import BaseModel
import requests
import os

import chromadb
from chromadb.utils import embedding_functions

from utils.pipelines.main import get_last_user_message, get_system_messages, add_or_update_system_message


class Pipeline:
    class Valves(BaseModel):
        # List target pipeline ids (models) that this filter will be connected to.
        # If you want to connect this filter to all pipelines, you can set pipelines to ["*"]
        # e.g. ["llama3:latest", "gpt-3.5-turbo"]
        pipelines: List[str] = []

        # Assign a priority level to the filter pipeline.
        # The priority level determines the order in which the filter pipelines are executed.
        # The lower the number, the higher the priority.
        priority: int = 0

        # Valves
        todo_app_url: str = os.getenv("TODO_API_BASE_URL", "http://host.docker.internal:3002")
        ollama_api_url: str = os.getenv("OLLAMA_API_URL", "http://host.docker.internal:11434")

        SYSTEM_PROMPT_TEMPLATE: str



    def __init__(self):
        # Pipeline filters are only compatible with Open WebUI
        # You can think of filter pipeline as a middleware that can be used to edit the form data before it is sent to the OpenAI API.
        self.type = "filter"

        # Optionally, you can set the id and name of the pipeline.
        # Best practice is to not specify the id so that it can be automatically inferred from the filename, so that users can install multiple versions of the same pipeline.
        # The identifier must be unique across all pipelines.
        # The identifier must be an alphanumeric string that can include underscores or hyphens. It cannot contain spaces, special characters, slashes, or backslashes.
        # self.id = "call_api_filter_pipeline"
        self.name = "Call Api Filter"

        # Initialize
        self.valves = self.Valves(
            **{
                "pipelines": ["*"],
                "todo_app_url": os.getenv("TODO_API_BASE_URL", "http://host.docker.internal:3002"),
                "ollama_api_url": os.getenv("OLLAMA_API_URL", "http://host.docker.internal:11434"),
                "SYSTEM_PROMPT_TEMPLATE": """
                    Use the following documentation as your knowledge about API endpoint, inside <documentation></documentation> XML tags.
                    <documentation>
                        {{CONTEXT}}
                    </documentation>

                    When answer to user:
                    - If you don't know how to perform, just say that you don't know to perform it.
                    - If you don't know when you are not sure, ask for clarification.
                    - Don't provide any information that you don't know.
                    Avoid mentioning that you obtained the information from the context.
                    And answer according to the language of the user's question.

                    Output in the format of curl command.
                """,
            }
        )

        sentence_transformer_ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")

        chroma_client = chromadb.Client()
        chroma_client.delete_collection(name="api_documentation")
        self.collection = chroma_client.create_collection(name="api_documentation", embedding_function=sentence_transformer_ef)

        self.collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
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

    async def on_valves_updated(self):
        # This function is called when the valves are updated.
        pass

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        print(f"inlet:{__name__}")
        print(f"Inlet Body Input: {body}")

        messages = body["messages"]
        user_message = get_last_user_message(messages)
        system_message = get_system_messages(messages)

        print(f"User message: {user_message}")
        system_prompt = self.valves.SYSTEM_PROMPT_TEMPLATE.replace(
            "{{CONTEXT}}", system_message
        )

        print(system_prompt)
        messages = add_or_update_system_message(
            system_prompt, body["messages"]
        )

        body = {**body, "messages": messages}
        print(f"Inlet Body Output: {body}")
        return body

    async def outlet(self, body: dict, user: Optional[dict] = None) -> dict:
        print(f"outlet:{__name__}")
        print(f"Outlet Body Input: {body}")

        # messages = body["messages"]
        # assistant_message = get_last_assistant_message(messages)

        # print(f"Assistant message: {assistant_message}")

        # # Translate assistant message
        # translated_assistant_message = self.translate(
        #     assistant_message,
        #     self.valves.source_assistant,
        #     self.valves.target_assistant,
        # )

        # print(f"Translated assistant message: {translated_assistant_message}")

        # for message in reversed(messages):
        #     if message["role"] == "assistant":
        #         message["content"] = translated_assistant_message
        #         break

        # body = {**body, "messages": messages}
        print(f"Outlet Body Output: {body}")
        return body
