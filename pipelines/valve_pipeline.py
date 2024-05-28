from typing import List, Optional
from schemas import OpenAIChatMessage


class Pipeline:
    def __init__(self):
        # Pipeline valves are only compatible with Open WebUI
        # You can think of valve pipeline as a middleware that can be used to edit the form data before it is sent to the OpenAI API.
        self.valve = True
        self.id = "valve_pipeline"
        self.name = "Valve"

        # Assign a priority level to the valve pipeline.
        # The priority level determines the order in which the valve pipelines are executed.
        # The lower the number, the higher the priority.
        self.priority = 0

        # List target pipelines (models) that this valve will be connected to.
        self.pipelines = [
            {"id": "llama3:latest"},
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

    async def control_valve(self, body: dict, user: Optional[dict] = None) -> dict:
        print(f"get_response:{__name__}")

        print(body)
        print(user)

        return body
