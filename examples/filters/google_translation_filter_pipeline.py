"""
title: Google Translate Filter
author: SimonOriginal
date: 2024-06-28
version: 1.0
license: MIT
description: This pipeline integrates Google Translate for automatic translation of user and assistant messages 
without requiring an API key. It supports multilingual communication by translating based on specified source 
and target languages.
"""

from typing import List, Optional
from schemas import OpenAIChatMessage
from pydantic import BaseModel
import requests
import os
import time

from utils.pipelines.main import get_last_user_message, get_last_assistant_message

class Pipeline:
    class Valves(BaseModel):
        pipelines: List[str] = []
        priority: int = 0
        source_user: Optional[str] = "auto"
        target_user: Optional[str] = "en"
        source_assistant: Optional[str] = "en"
        target_assistant: Optional[str] = "uk"

    def __init__(self):
        # Initialize the pipeline type and name
        self.type = "filter"
        self.name = "Google Translate Filter"
        
        # Initialize Valves with default values
        self.valves = self.Valves(
            **{
                "pipelines": ["*"],
            }
        )

    async def on_startup(self):
        # Function called when the server is started
        print(f"on_startup:{__name__}")
        pass

    async def on_shutdown(self):
        # Function called when the server is stopped
        print(f"on_shutdown:{__name__}")
        pass

    async def on_valves_updated(self):
        # Function called when the valves are updated
        pass

    def translate(self, text: str, source: str, target: str) -> str:
        # Function to translate text using Google Translate
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": source,
            "tl": target,
            "dt": "t",
            "q": text,
        }
        
        try:
            # Make a GET request to Google Translate API
            r = requests.get(url, params=params)
            r.raise_for_status()  # Raise an exception for bad status codes
            
            # Parse the JSON response
            result = r.json()
            translated_text = ''.join([sentence[0] for sentence in result[0]])  # Combine all translated sentences into one string
            return translated_text
        except requests.exceptions.RequestException as e:
            # Handle network errors, retrying after a short pause
            print(f"Network error: {e}")
            time.sleep(1)  # Pause before retrying
            return self.translate(text, source, target)  # Retry translation
        except Exception as e:
            # Handle other exceptions
            print(f"Error translating text: {e}")
            return text  # Return original text in case of error

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        # Function to process incoming messages from the user
        print(f"inlet:{__name__}")

        messages = body["messages"]
        user_message = get_last_user_message(messages)

        print(f"User message: {user_message}")

        # Translate user message
        translated_user_message = self.translate(
            user_message,
            self.valves.source_user,
            self.valves.target_user,
        )

        print(f"Translated user message: {translated_user_message}")

        # Update the translated message in the messages list
        for message in reversed(messages):
            if message["role"] == "user":
                message["content"] = translated_user_message
                break

        body = {**body, "messages": messages}
        return body

    async def outlet(self, body: dict, user: Optional[dict] = None) -> dict:
        # Function to process outgoing messages from the assistant
        print(f"outlet:{__name__}")

        messages = body["messages"]
        assistant_message = get_last_assistant_message(messages)

        print(f"Assistant message: {assistant_message}")

        # Translate assistant message
        translated_assistant_message = self.translate(
            assistant_message,
            self.valves.source_assistant,
            self.valves.target_assistant,
        )

        print(f"Translated assistant message: {translated_assistant_message}")

        # Update the translated message in the messages list
        for message in reversed(messages):
            if message["role"] == "assistant":
                message["content"] = translated_assistant_message
                break

        body = {**body, "messages": messages}
        return body
