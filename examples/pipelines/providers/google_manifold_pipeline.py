"""A manifold to integrate Google's GenAI models into Open-WebUI"""

from typing import List, Union, Iterator
import os

from pydantic import BaseModel

import google.generativeai as genai


class Pipeline:
    """Google GenAI pipeline"""

    class Valves(BaseModel):
        """Options to change from the WebUI"""

        GOOGLE_API_KEY: str = ""

    def __init__(self):
        self.type = "manifold"
        self.id = "google_genai"
        self.name = "Google: "

        self.valves = self.Valves(**{"GOOGLE_API_KEY": os.getenv("GOOGLE_API_KEY", "")})
        self.pipelines = []

        genai.configure(api_key=self.valves.GOOGLE_API_KEY)
        self.update_pipelines()

    async def on_startup(self) -> None:
        """This function is called when the server is started."""

        print(f"on_startup:{__name__}")

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
            except Exception:
                self.pipelines = [
                    {
                        "id": "error",
                        "name": "Could not fetch models from Google, please update the API Key in the valves.",
                    }
                ]
        else:
            self.pipelines = []

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Iterator]:
        """The pipe function (connects open-webui to google-genai)

        Args:
            user_message (str): The last message input by the user
            model_id (str): The model to use
            messages (List[dict]): The chat history
            body (dict): The raw request body in OpenAI's "chat/completions" style

        Returns:
            str: The complete response

        Yields:
            Iterator[str]: Yields a new message part every time it is received
        """

        print(f"pipe:{__name__}")

        system_prompt = None
        google_messages = []
        for message in messages:
            google_role = ""
            if message["role"] == "user":
                google_role = "user"
            elif message["role"] == "assistant":
                google_role = "model"
            elif message["role"] == "system":
                system_prompt = message["content"]
                continue  # System promt is not inyected as a message
            google_messages.append(
                genai.protos.Content(
                    role=google_role,
                    parts=[
                        genai.protos.Part(
                            text=message["content"],
                        ),
                    ],
                )
            )

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
            return ""

        return response.text
