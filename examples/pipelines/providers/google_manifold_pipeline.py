"""A manifold to integrate Google's GenAI models into Open-WebUI"""

from typing import List, Union, Generator
import base64
import re

from io import BytesIO
from pydantic import BaseModel

import google.generativeai as genai
from PIL import Image


class Pipeline:
    """Google GenAI pipeline"""

    class Valves(BaseModel):
        """Options to change from the WebUI"""

        GOOGLE_API_KEY: str = ""

    def __init__(self):
        self.type = "manifold"
        self.id = "google_genai"
        self.name = "Google: "

        self.valves = self.Valves()
        self.pipelines = []

    async def on_startup(self) -> None:
        """This function is called when the server is started."""

        print(f"on_startup:{__name__}")
        genai.configure(api_key=self.valves.GOOGLE_API_KEY)
        self.update_pipelines()

    async def on_shutdown(self) -> None:
        """This function is called when the server is stopped."""

        print(f"on_shutdown:{__name__}")

    async def on_valves_updated(self) -> None:
        """This function is called when the valves are updated."""

        print(f"on_valves_updated:{__name__}")
        genai.configure(api_key=self.valves.GOOGLE_API_KEY)
        self.update_pipelines()

    def update_pipelines(self) -> None:
        """Update the available models from Google GenAI"""

        if self.valves.GOOGLE_API_KEY:
            try:
                models = genai.list_models()
                self.pipelines = [
                    {
                        "id": model.name[7:],  # the "models/" part messeses up the URL
                        "name": model.display_name,
                    }
                    for model in models
                    if "generateContent" in model.supported_generation_methods
                    if model.name[:7] == "models/"
                ]
                return
            except Exception:
                pass
        self.pipelines = [
            {
                "id": "error",
                "name": "Could not fetch models from Google, please update the API Key in the valves.",
            }
        ]

    def base64_url_to_image(self, base64_url: str) -> Image.Image:
        """Convert a base64-encoded url image into a Pillow Image

        Args:
            base64_url (str): The base64-encoded url

        Returns:
            Image.Image: The image
        """

        # Extract the base64 part (it starts after the comma)
        base64_data = re.sub("^data:image/.+;base64,", "", base64_url)

        # Decode the base64 string
        image_data = base64.b64decode(base64_data)

        # Convert bytes data to an image
        image = Image.open(BytesIO(image_data))

        return image

    def messages_to_google_format(
        self, messages: List[dict]
    ) -> List[genai.protos.Content]:
        """Convert the OpenAI formatted messages from Open-WebUI into Google GenAI formatted ones

        Args:
            messages (List[dict]): The list of OpenAI formatted messages

        Returns:
            List[genai.protos.Content]: The list of Google GenAI formatted messages
        """

        role_map = {"user": "user", "assistant": "model"}

        google_messages = []
        for message in messages:
            google_role = role_map.get(message["role"])

            # Skip if message is not from user or assistant
            if not google_role:
                continue

            parts = []
            content = message["content"]

            if isinstance(content, List):
                for part in content:
                    if part["type"] == "text":
                        parts.append(genai.protos.Part(text=part["text"]))
                    elif part["type"] == "image_url":
                        parts.append(self.base64_url_to_image(part["image_url"]["url"]))
            else:
                parts.append(genai.protos.Part(text=content))

            google_messages.append(genai.protos.Content(role=google_role, parts=parts))

        return google_messages

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator]:
        """The pipe function (connects open-webui to google-genai)

        Args:
            user_message (str): The last message input by the user
            model_id (str): The model to use
            messages (List[dict]): The chat history
            body (dict): The raw request body in OpenAI's "chat/completions" style

        Returns:
            str: The complete response

        Yields:
            Generator[str]: Yields a new message part every time it is received
        """

        print(f"pipe:{__name__}")

        system_prompt = next(
            (msg["content"] for msg in reversed(messages) if msg["role"] == "system"),
            None,
        )

        google_messages = self.messages_to_google_format(messages)

        response = genai.GenerativeModel(
            f"models/{model_id}",  # we have to add the "models/" part again
            system_instruction=system_prompt,
        ).generate_content(
            google_messages,
            stream=body["stream"],
        )

        if body["stream"]:
            for chunk in response:
                yield chunk.text
        else:
            return response.text
