from typing import List, Union, Generator, Iterator
from schemas import OpenAIChatMessage


class Pipeline:
    def __init__(self):
        # You can also set the pipelines that are available in this pipeline.
        # Set manifold to True if you want to use this pipeline as a manifold.
        # Manifold pipelines can have multiple pipelines.
        self.type = "manifold"

        self.id = "manifold_pipeline"
        # Optionally, you can set the name of the manifold pipeline.
        self.name = "Manifold: "
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
        # This is where you can add your custom pipelines like RAG.'
        print(f"pipe:{__name__}")

        print(messages)
        print(user_message)
        print(body)

        return f"{model_id} response to: {user_message}"
