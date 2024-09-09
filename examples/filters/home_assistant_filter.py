"""
title: HomeAssistant Filter Pipeline
author: Andrew Tait Gehrhardt
date: 2024-06-15
version: 1.0
license: MIT
description: A pipeline for controlling Home Assistant entities based on their easy names. Only supports lights at the moment.
requirements: pytz, difflib
"""
import requests
from typing import Literal, Dict, Any
from datetime import datetime
import pytz
from difflib import get_close_matches

from blueprints.function_calling_blueprint import Pipeline as FunctionCallingBlueprint

class Pipeline(FunctionCallingBlueprint):
    class Valves(FunctionCallingBlueprint.Valves):
        HOME_ASSISTANT_URL: str = ""
        HOME_ASSISTANT_TOKEN: str = ""

    class Tools:
        def __init__(self, pipeline) -> None:
            self.pipeline = pipeline

        def get_current_time(self) -> str:
            """
            Get the current time in EST.

            :return: The current time in EST.
            """
            now_est = datetime.now(pytz.timezone('US/Eastern'))  # Get the current time in EST
            current_time = now_est.strftime("%I:%M %p")  # %I for 12-hour clock, %M for minutes, %p for am/pm
            return f"ONLY RESPOND 'Current time is {current_time}'"

        def get_all_lights(self) -> Dict[str, Any]:
            """
            Lists my lights.
            Shows me my lights.
            Get a dictionary of all lights in my home.

            :return: A dictionary of light entity names and their IDs.
            """
            if not self.pipeline.valves.HOME_ASSISTANT_URL or not self.pipeline.valves.HOME_ASSISTANT_TOKEN:
                return {"error": "Home Assistant URL or token not set, ask the user to set it up."}
            else:
                url = f"{self.pipeline.valves.HOME_ASSISTANT_URL}/api/states"
                headers = {
                    "Authorization": f"Bearer {self.pipeline.valves.HOME_ASSISTANT_TOKEN}",
                    "Content-Type": "application/json",
                }

                response = requests.get(url, headers=headers)
                response.raise_for_status()  # Raises an HTTPError for bad responses
                data = response.json()

                lights = {entity["attributes"]["friendly_name"]: entity["entity_id"]
                          for entity in data if entity["entity_id"].startswith("light.")}

                return lights

        def control_light(self, name: str, state: Literal['on', 'off']) -> str:
            """
            Turn a light on or off based on its name.

            :param name: The friendly name of the light.
            :param state: The desired state ('on' or 'off').
            :return: The result of the operation.
            """
            if not self.pipeline.valves.HOME_ASSISTANT_URL or not self.pipeline.valves.HOME_ASSISTANT_TOKEN:
                return "Home Assistant URL or token not set, ask the user to set it up."

            # Normalize the light name by converting to lowercase and stripping extra spaces
            normalized_name = " ".join(name.lower().split())

            # Get a dictionary of all lights
            lights = self.get_all_lights()
            if "error" in lights:
                return lights["error"]

            # Find the closest matching light name
            light_names = list(lights.keys())
            closest_matches = get_close_matches(normalized_name, light_names, n=1, cutoff=0.6)

            if not closest_matches:
                return f"Light named '{name}' not found."

            best_match = closest_matches[0]
            light_id = lights[best_match]

            url = f"{self.pipeline.valves.HOME_ASSISTANT_URL}/api/services/light/turn_{state}"
            headers = {
                "Authorization": f"Bearer {self.pipeline.valves.HOME_ASSISTANT_TOKEN}",
                "Content-Type": "application/json",
            }
            payload = {
                "entity_id": light_id
            }

            response = requests.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                return f"ONLY RESPOND 'Will do' TO THE USER. DO NOT SAY ANYTHING ELSE!"
            else:
                return f"ONLY RESPOND 'Couldn't find light' TO THE USER. DO NOT SAY ANYTHING ELSE!"

    def __init__(self):
        super().__init__()
        self.name = "My Tools Pipeline"
        self.valves = self.Valves(
            **{
                **self.valves.model_dump(),
                "pipelines": ["*"],  # Connect to all pipelines
            },
        )
        self.tools = self.Tools(self)
