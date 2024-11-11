"""A manifold to integrate OpenAI's ImageGen models into Open-WebUI"""

import os
from typing import List, Union, Generator, Iterator

from pydantic import BaseModel

from openai import OpenAI

class Pipeline:
    """OpenAI ImageGen pipeline"""

    class Valves(BaseModel):
        """Options to change from the WebUI"""

        OPENAI_API_BASE_URL: str = "https://api.openai.com/v1"
        OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY")
        IMAGE_SIZE: str = "1792x1024"
        NUM_IMAGES: int = 4

    def __init__(self):
        self.type = "manifold"
        self.name = "Inverse Designer: "

        self.valves = self.Valves()
        self.client = OpenAI(
            base_url=self.valves.OPENAI_API_BASE_URL,
            api_key=self.valves.OPENAI_API_KEY,
        )

        self.pipelines = self.get_openai_assistants()

    async def on_startup(self) -> None:
        """This function is called when the server is started."""
        print(f"on_startup:{__name__}")

    async def on_shutdown(self):
        """This function is called when the server is stopped."""
        print(f"on_shutdown:{__name__}")

    async def on_valves_updated(self):
        """This function is called when the valves are updated."""
        print(f"on_valves_updated:{__name__}")
        self.client = OpenAI(
            base_url=self.valves.OPENAI_API_BASE_URL,
            api_key=self.valves.OPENAI_API_KEY,
        )
        self.pipelines = self.get_openai_assistants()

    def get_openai_assistants(self) -> List[dict]:
        """Get the available ImageGen models from OpenAI

        Returns:
            List[dict]: The list of ImageGen models
        """

        if self.valves.OPENAI_API_KEY:
            models = self.client.models.list()
            return [
                {
                    "id": model.id,
                    "name": model.id,
                }
                for model in models
                if "dall-e" in model.id
            ]

        return []

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        print(f"pipe:{__name__}")

        message = ""
        # Use NUM_IMAGES to determine number of API calls
        for _ in range(self.valves.NUM_IMAGES):
            response = self.client.images.generate(
                model=model_id,
                prompt=user_message,
                size=self.valves.IMAGE_SIZE,
                n=1,  # Always generate 1 image per call
            )


            for image in response.data:
                if image.url:
                    message += "![image](" + image.url + ")\n"

        yield message
