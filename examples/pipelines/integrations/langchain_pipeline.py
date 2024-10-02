import os
from typing import Generator, Iterator, List, Union

from langchain.chat_models.base import init_chat_model
from pydantic import BaseModel


class Pipeline:
    class Valves(BaseModel):
        OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY")
        MODEL: str = os.getenv("MODEL", "gpt-4o-mini")
        MODEL_PROVIDER: str = os.getenv("MODEL_PROVIDER", "")

        pass

    def __init__(self):
        # Optionally, you can set the id and name of the pipeline.
        # Best practice is to not specify the id so that it can be automatically inferred from the filename, so that users can install multiple versions of the same pipeline.
        # The identifier must be unique across all pipelines.
        # The identifier must be an alphanumeric string that can include underscores or hyphens. It cannot contain spaces, special characters, slashes, or backslashes.
        self.id = "langchain_pipeline"
        self.name = "LangChain Pipeline"
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

    def pipe(self, user_message: str, model_id: str, messages: List[dict], body: dict) -> Union[str, Generator, Iterator]:
        # This is where you can add your custom pipelines like RAG.
        print(f"pipe:{__name__}")

        ## CUSTOM CHAIN
        MODEL = self.valves.MODEL
        MODEL_PROVIDER = self.valves.MODEL_PROVIDER
        llm = init_chat_model(model=MODEL, model_provider=MODEL_PROVIDER)
        # e.g. chain = prompt | llm
        chain = llm
        # ...
        ## CUSTOM CHAIN

        print(body)

        try:
            if body["stream"]:
                return (chunk.content for chunk in chain.stream(messages))
            else:
                return chain.invoke(messages).content
        except Exception as e:
            return f"Error: {e}"

    # CUSTOM CHAIN A FUNCTION
    def chain(self):
        MODEL = self.valves.MODEL
        MODEL_PROVIDER = self.valves.MODEL_PROVIDER
        llm = init_chat_model(model=MODEL, model_provider=MODEL_PROVIDER)
        # e.g. chain = prompt | llm
        chain = llm
        return chain
