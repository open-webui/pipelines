from typing import List, Optional
from pydantic import BaseModel
from schemas import OpenAIChatMessage
import os
import requests
import json

from utils.main import (
    get_last_user_message,
    add_or_update_system_message,
    get_function_specs,
)
from typing import Literal


class Pipeline:
    def __init__(self):
        # Pipeline filters are only compatible with Open WebUI
        # You can think of filter pipeline as a middleware that can be used to edit the form data before it is sent to the OpenAI API.
        self.type = "filter"

        # Assign a unique identifier to the pipeline.
        # The identifier must be unique across all pipelines.
        # The identifier must be an alphanumeric string that can include underscores or hyphens. It cannot contain spaces, special characters, slashes, or backslashes.
        self.id = "function_calling_filter_pipeline"
        self.name = "Function Calling Filter"

        class Valves(BaseModel):
            # List target pipeline ids (models) that this filter will be connected to.
            # If you want to connect this filter to all pipelines, you can set pipelines to ["*"]
            pipelines: List[str] = []

            # Assign a priority level to the filter pipeline.
            # The priority level determines the order in which the filter pipelines are executed.
            # The lower the number, the higher the priority.
            priority: int = 0

            # Valves for function calling
            OPENAI_API_BASE_URL: str
            OPENAI_API_KEY: str
            TASK_MODEL: str
            TEMPLATE: str

            OPENWEATHERMAP_API_KEY: str = ""

        # Initialize valves
        self.valves = Valves(
            **{
                "pipelines": ["*"],  # Connect to all pipelines
                "OPENAI_API_BASE_URL": "https://api.openai.com/v1",
                "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY"),
                "TASK_MODEL": "gpt-3.5-turbo",
                "TEMPLATE": """Use the following context as your learned knowledge, inside <context></context> XML tags.
<context>
    {{CONTEXT}}
</context>

When answer to user:
- If you don't know, just say that you don't know.
- If you don't know when you are not sure, ask for clarification.
Avoid mentioning that you obtained the information from the context.
And answer according to the language of the user's question.""",
            }
        )

        class Functions:
            def __init__(self, pipeline) -> None:
                self.pipeline = pipeline

            def get_current_weather(
                self,
                location: str,
                unit: Literal["metric", "fahrenheit"] = "fahrenheit",
            ) -> str:
                """
                Get the current weather for a location. If the location is not found, return an empty string.

                :param location: The location to get the weather for.
                :param unit: The unit to get the weather in. Default is fahrenheit.
                :return: The current weather for the location.
                """

                # https://openweathermap.org/api

                if self.pipeline.valves.OPENWEATHERMAP_API_KEY == "":
                    return "OpenWeatherMap API Key not set, ask the user to set it up."
                else:
                    units = "imperial" if unit == "fahrenheit" else "metric"
                    params = {
                        "q": location,
                        "appid": self.pipeline.valves.OPENWEATHERMAP_API_KEY,
                        "units": units,
                    }

                    response = requests.get(
                        "http://api.openweathermap.org/data/2.5/weather", params=params
                    )
                    response.raise_for_status()  # Raises an HTTPError for bad responses
                    data = response.json()

                    weather_description = data["weather"][0]["description"]
                    temperature = data["main"]["temp"]

                    return f"{location}: {weather_description.capitalize()}, {temperature}°{unit.capitalize()[0]}"

            def calculator(self, equation: str) -> str:
                """
                Calculate the result of an equation.

                :param equation: The equation to calculate.
                """

                # Avoid using eval in production code
                # https://nedbatchelder.com/blog/201206/eval_really_is_dangerous.html
                try:
                    result = eval(equation)
                    return f"{equation} = {result}"
                except Exception as e:
                    print(e)
                    return "Invalid equation"

        self.functions = Functions(self)

    async def on_startup(self):
        # This function is called when the server is started.
        print(f"on_startup:{__name__}")
        pass

    async def on_shutdown(self):
        # This function is called when the server is stopped.
        print(f"on_shutdown:{__name__}")
        pass

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        # If title generation is requested, skip the function calling filter
        if body.get("title", False):
            return body

        print(f"pipe:{__name__}")
        print(user)

        # Get the last user message
        user_message = get_last_user_message(body["messages"])

        # Get the function specs
        function_specs = get_function_specs(self.functions)

        # System prompt for function calling
        fc_system_prompt = (
            f"Functions: {json.dumps(function_specs, indent=2)}"
            + """
If a function doesn't match the query, return an empty string. Else, pick a function, fill in the parameters from the function's schema, and return it in the format { "name": \"functionName\", "parameters": { "key": "value" } }. Only pick a function if the user asks.  Only return the object. Do not return any other text."
"""
        )

        r = None
        try:
            # Call the OpenAI API to get the function response
            r = requests.post(
                url=f"{self.valves.OPENAI_API_BASE_URL}/chat/completions",
                json={
                    "model": self.valves.TASK_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": fc_system_prompt,
                        },
                        {
                            "role": "user",
                            "content": "History:\n"
                            + "\n".join(
                                [
                                    f"{message['role']}: {message['content']}"
                                    for message in body["messages"][::-1][:4]
                                ]
                            )
                            + f"Query: {user_message}",
                        },
                    ],
                    # TODO: dynamically add response_format?
                    # "response_format": {"type": "json_object"},
                },
                headers={
                    "Authorization": f"Bearer {self.valves.OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                stream=False,
            )
            r.raise_for_status()

            response = r.json()
            content = response["choices"][0]["message"]["content"]

            # Parse the function response
            if content != "":
                result = json.loads(content)
                print(result)

                # Call the function
                if "name" in result:
                    function = getattr(self.functions, result["name"])
                    function_result = None
                    try:
                        function_result = function(**result["parameters"])
                    except Exception as e:
                        print(e)

                    # Add the function result to the system prompt
                    if function_result:
                        system_prompt = self.valves.TEMPLATE.replace(
                            "{{CONTEXT}}", function_result
                        )

                        print(system_prompt)
                        messages = add_or_update_system_message(
                            system_prompt, body["messages"]
                        )

                        # Return the updated messages
                        return {**body, "messages": messages}

        except Exception as e:
            print(f"Error: {e}")

            if r:
                try:
                    print(r.json())
                except:
                    pass

        return body
