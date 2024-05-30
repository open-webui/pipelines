from typing import List, Optional
from schemas import OpenAIChatMessage
import os


from pydantic import BaseModel
from langfuse import Langfuse
from langfuse.decorators import langfuse_context, observe


class Pipeline:
    def __init__(self):
        # Pipeline filters are only compatible with Open WebUI
        # You can think of filter pipeline as a middleware that can be used to edit the form data before it is sent to the OpenAI API.
        self.type = "filter"

        # Optionally, you can set the id and name of the pipeline.
        # Assign a unique identifier to the pipeline.
        # The identifier must be unique across all pipelines.
        # The identifier must be an alphanumeric string that can include underscores or hyphens. It cannot contain spaces, special characters, slashes, or backslashes.
        self.id = "langfuse_filter_pipeline"
        self.name = "Langfuse Filter"

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
            secret_key: str
            public_key: str
            host: str

        # Initialize
        self.valves = Valves(
            **{
                "pipelines": ["*"],  # Connect to all pipelines
                "secret_key": os.getenv("LANGFUSE_SECRET_KEY"),
                "public_key": os.getenv("LANGFUSE_PUBLIC_KEY"),
                "host": os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
            }
        )

        self.langfuse = None
        pass

    async def on_startup(self):
        # This function is called when the server is started.
        print(f"on_startup:{__name__}")
        self.set_langfuse()
        pass

    async def on_shutdown(self):
        # This function is called when the server is stopped.
        print(f"on_shutdown:{__name__}")
        self.langfuse.flush()
        pass

    async def on_valves_updated(self):
        # This function is called when the valves are updated.

        self.set_langfuse()
        pass

    def set_langfuse(self):
        self.langfuse = Langfuse(
            secret_key=self.valves.secret_key,
            public_key=self.valves.public_key,
            host=self.valves.host,
            debug=True,
        )
        self.langfuse.auth_check()

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        print(f"inlet:{__name__}")

        trace = self.langfuse.trace(
            name=f"filter:{__name__}",
            input=body,
            user_id=user["id"],
            metadata={"name": user["name"]},
        )

        print(trace.get_trace_url())

        return body
