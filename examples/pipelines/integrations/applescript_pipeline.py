from typing import List, Union, Generator, Iterator
from schemas import OpenAIChatMessage
import requests


from subprocess import call


class Pipeline:
    def __init__(self):
        # Optionally, you can set the id and name of the pipeline.
        # Best practice is to not specify the id so that it can be automatically inferred from the filename, so that users can install multiple versions of the same pipeline.
        # The identifier must be unique across all pipelines.
        # The identifier must be an alphanumeric string that can include underscores or hyphens. It cannot contain spaces, special characters, slashes, or backslashes.
        # self.id = "applescript_pipeline"
        self.name = "AppleScript Pipeline"
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

        OLLAMA_BASE_URL = "http://localhost:11434"
        MODEL = "llama3"

        if body.get("title", False):
            print("Title Generation")
            return "AppleScript Pipeline"
        else:
            if "user" in body:
                print("######################################")
                print(f'# User: {body["user"]["name"]} ({body["user"]["id"]})')
                print(f"# Message: {user_message}")
                print("######################################")

            commands = user_message.split(" ")

            if commands[0] == "volume":

                try:
                    commands[1] = int(commands[1])
                    if 0 <= commands[1] <= 100:
                        call(
                            [f"osascript -e 'set volume output volume {commands[1]}'"],
                            shell=True,
                        )
                except:
                    pass

            payload = {
                "model": MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": f"You are an agent of the AppleScript Pipeline. You have the power to control the volume of the system.",
                    },
                    {"role": "user", "content": user_message},
                ],
                "stream": body["stream"],
            }

            try:
                r = requests.post(
                    url=f"{OLLAMA_BASE_URL}/v1/chat/completions",
                    json=payload,
                    stream=True,
                )

                r.raise_for_status()

                if body["stream"]:
                    return r.iter_lines()
                else:
                    return r.json()
            except Exception as e:
                return f"Error: {e}"
