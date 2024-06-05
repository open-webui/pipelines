"""A manifold to integrate OpenAI's assistants into Open-WebUI"""

from typing import Any, List, Union, Generator, Iterator
import shelve
import os

import io
import base64
from PIL import Image


from pydantic import BaseModel


from openai import OpenAI, Stream
from openai.types.chat.chat_completion_chunk import (
    ChatCompletionChunk,
    Choice,
    ChoiceDelta,
)
from openai.types.completion_usage import CompletionUsage

from openai.types.beta import Thread

from openai.types.beta.assistant_stream_event import (
    AssistantStreamEvent,
    ThreadRunCreated,
    ThreadRunStepDelta,
    ThreadRunStepCompleted,
    ThreadMessageDelta,
    ThreadRunStepCreated,
    ThreadRunCompleted,
)

from openai.types.beta.threads.run import Usage
from openai.types.beta.threads.runs import ToolCallsStepDetails
from openai.types.beta.threads import MessageDelta, TextDeltaBlock, ImageFileDeltaBlock


class Pipeline:
    """OpenAI assistants pipeline"""

    class Valves(BaseModel):
        """Options to change from the WebUI"""

        OPENAI_API_BASE_URL: str = "https://api.openai.com/v1"
        OPENAI_API_KEY: str = ""

    def __init__(self):
        self.type = "manifold"
        self.name = "Assistant: "

        self.valves = self.Valves(**{"OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", "")})
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
        """Get the available assistants from OpenAI

        Returns:
            List[dict]: The list of assistants
        """

        if self.valves.OPENAI_API_KEY:
            assistants = self.client.beta.assistants.list()
            return [
                {
                    "id": assistant.id,
                    "name": assistant.name,
                }
                for assistant in assistants
            ]

        return []

    def get_thread(self, chat_id: str) -> Thread:
        """fetch thread for chat_id or create if necessary

        Args:
            chat_id (str): OPEN-WEBUI's chat ID

        Returns:
            Thread: OpenAI's thread
        """

        with shelve.open("/data/threads.db", writeback=True) as store:
            if chat_id in store:
                return self.client.beta.threads.retrieve(store[chat_id])

            thread = self.client.beta.threads.create()
            store[chat_id] = thread.id
            return thread

    def get_image(self, file_id: str):
        response = self.client.files.content(file_id=file_id)
        image_data = response.content
        image = Image.open(io.BytesIO(image_data))
        format_to_mime = {
            'JPEG': 'image/jpeg',
            'JPG': 'image/jpeg',
            'PNG': 'image/png',
            'GIF': 'image/gif',
            'BMP': 'image/bmp',
            'ICO': 'image/x-icon',
            'WEBP': 'image/webp',
            'TIFF': 'image/tiff',
            'TIF': 'image/tiff'
        }

        mime_type = format_to_mime.get(image.format.upper(), 'application/octet-stream')
        base64_encoded_image = base64.b64encode(image_data).decode('utf-8')
        return f"data:{mime_type};base64,{base64_encoded_image}"

    def process_openai_assistant_stream(
        self, run: Stream[AssistantStreamEvent]
    ) -> Iterator[Any]:
        """Convert OpenAI's Assistant stream to a old completions stream

        Args:
            run (Stream[AssistantStreamEvent]): The assistants API streaming format

        Yields:
            Iterator[ChatCompletionChunk]: The old streaming format
        """

        model = ""
        openai_id = ""
        created = 0

        for step in run:
            message:str = ""
            usage = None
            finish_reason = None

            # Run created
            if isinstance(step, ThreadRunCreated):
                model = step.data.model
                openai_id = step.data.id
                created = step.data.created_at

            # Code started
            if isinstance(step, ThreadRunStepCreated) and isinstance(step.data.step_details, ToolCallsStepDetails):  # fmt: skip
                openai_id = step.data.id
                message += "\n```python\n"

            # Code
            if isinstance(step, ThreadRunStepDelta):
                input_value = step.data.delta.step_details.tool_calls[0].code_interpreter.input  # fmt: skip
                if input_value:
                    message += input_value

            # Code ended
            if isinstance(step, ThreadRunStepCompleted) and isinstance(step.data.step_details, ToolCallsStepDetails):  # fmt: skip
                message += "\n```\n"  # End previous code

                # This is to show the output of the execution, but it didn's seem to work
                # outputs_value = step.data.delta.step_details.tool_calls[0].code_interpreter.outputs  # fmt: skip
                # if outputs_value:
                #     message += (
                #         "```\n"
                #         + "\n".join([out.logs for out in outputs_value])
                #         + "\n```\n"
                #     )

            # Message
            if isinstance(step, ThreadMessageDelta) and isinstance(step.data.delta, MessageDelta):  # fmt: skip
                for value in step.data.delta.content:
                    if isinstance(value, TextDeltaBlock):
                        message += str(value.text.value)
                    elif isinstance(value, ImageFileDeltaBlock):
                        url_image = self.get_image(value.image_file.file_id)
                        print(url_image)
                        message += "![image](" + url_image + ")"
            
            # End
            if isinstance(step, ThreadRunCompleted) and isinstance(step.data.usage, Usage):  # fmt: skip
                usage = CompletionUsage(
                    completion_tokens=step.data.usage.completion_tokens,
                    prompt_tokens=step.data.usage.prompt_tokens,
                    total_tokens=step.data.usage.total_tokens,
                )
                finish_reason = "stop"

            yield ChatCompletionChunk(
                id=openai_id,
                choices=[
                    Choice(
                        index=0,
                        delta=ChoiceDelta(content=message),
                        finish_reason=finish_reason,
                    ),
                ],
                created=created,
                model=model,
                object="chat.completion.chunk",
                usage=usage
            )

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        print(f"pipe:{__name__}")

        # Create or retieve thread
        thread = self.get_thread(body["chat_id"])

        # Add last message
        self.client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_message,
        )

        # Create a run
        run = self.client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=model_id,
            stream=True
        )

        # Translate the run into the old format
        return self.process_openai_assistant_stream(run)
