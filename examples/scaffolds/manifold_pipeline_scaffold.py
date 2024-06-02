from typing import List, Union, Generator, Iterator
from schemas import OpenAIChatMessage


class Pipeline:
    def __init__(self):
        # You can also set the pipelines that are available in this pipeline.
        # Set manifold to True if you want to use this pipeline as a manifold.
        # Manifold pipelines can have multiple pipelines.
        self.type = "manifold"

        # Optionally, you can set the id and name of the pipeline.
        # Best practice is to not specify the id so that it can be automatically inferred from the filename, so that users can install multiple versions of the same pipeline.
        # The identifier must be unique across all pipelines.
        # The identifier must be an alphanumeric string that can include underscores or hyphens. It cannot contain spaces, special characters, slashes, or backslashes.
        # self.id = "manifold_pipeline"

        # Optionally, you can set the name of the manifold pipeline.
        self.name = "Manifold: "

        # Define pipelines that are available in this manifold pipeline.
        # This is a list of dictionaries where each dictionary has an id and name.
        self.pipelines = [
            {
                "id": "pipeline-1",  # This will turn into `manifold_pipeline.pipeline-1`
                "name": "Pipeline 1",  # This will turn into `Manifold: Pipeline 1`
            },
            {
                "id": "pipeline-2",
                "name": "Pipeline 2",
            },
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

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        # This is where you can add your custom pipelines like RAG.
        print(f"pipe:{__name__}")

        # If you'd like to check for title generation, you can add the following check
        if body.get("title", False):
            print("Title Generation Request")

        print(messages)
        print(user_message)
        print(body)

        return f"{model_id} response to: {user_message}"
