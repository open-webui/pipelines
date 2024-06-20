from typing import List, Union, Generator, Iterator
from pydantic import BaseModel
import requests
import os
import json
import aiohttp

class Pipeline:
    class Valves(BaseModel):
        pipelines: List[str] = []
        priority: int = 0
        openai_base_url: str = "http://host.docker.internal:11434/v1"  # OpenAI Compatible URL

    def __init__(self):
        self.name = "Semantic Model Router"
        self.valves = self.Valves(
            **{
                "pipelines": ["*"],  # Connect to all pipelines
            }
        )

    async def on_startup(self):
        print(f"on_startup:{__name__}")
        pass

    async def on_shutdown(self):
        print(f"on_shutdown:{__name__}")
        pass

    async def default_chat(self, body: dict, content: str):
        messages = body.get("messages", [])
        url = f"{self.valves.openai_base_url}/chat/completions"
        payload = {
            "model": "eva",
            "messages": [
                {
                    "role": "user",
                    "content": content
                }
            ]
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        choices = response_data.get('choices', [])
                        if choices:
                            assistant_message = choices[0].get('message', {}).get('content', '')
                            print(assistant_message)
                            formatted_llm_response = f"REPEAT THIS BACK: MODEL - EVA {assistant_message}"
                            print(formatted_llm_response)
                            for message in messages:
                                message["content"] = formatted_llm_response
        except Exception as e:
            print(f"Error in default_chat: {e}")

    async def media_chat(self, body: dict, content: str):
        messages = body.get("messages", [])
        url = f"{self.valves.openai_base_url}/chat/completions"
        payload = {
            "model": "llama3:instruct",
            "messages": [
                {
                    "role": "user",
                    "content": content
                }
            ]
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        choices = response_data.get('choices', [])
                        if choices:
                            assistant_message = choices[0].get('message', {}).get('content', '')
                            print(assistant_message)
                            formatted_llm_response = f"REPEAT THIS BACK: MODEL - llama3:latest {assistant_message}"
                            print(formatted_llm_response)
                            for message in messages:
                                message["content"] = formatted_llm_response
        except Exception as e:
            print(f"Error in media_chat: {e}")

    def determine_intention(self, user_message: str) -> str:

        intentions = {
            'general_chatting()': 'The user is simply chatting with you and asking simple questions.',
            'media()': 'The user is asking about an image/picture/video',
        }

        url = f"{self.valves.openai_base_url}/chat/completions"
        payload = {
            "model": "gemma:2b-instruct-v1.1-q4_K_M",
            "messages": [
                {
                    "role": "user",
                    "content": f"""
                    <system_prompt>
                    You are an intention measurement machine. You will consider the USER_QUERY carefully and decide what their intention is.
                    You may select one of the following intentions from the object below:

                    {intentions}

                    <start_of_turn>user
                    USER_QUERY: 
                    {user_message}
                    <end_of_turn>
                    <start_of_turn>
                    YOU WILL RESPOND WITH ONLY A SINGLE WORD - The intention key value
                    model 
                    """
                }
            ]
        }
        try:
            response = requests.post(url, json=payload)
            print('REQUESTING!')
            if response.status == 200:
                response_data = response.json()
                choices = response_data.get('choices', [])
                if choices:
                    return choices[0].get('message', {}).get('content', '').strip()
        except Exception as e:
            print(f"Error in determine_intention: {e}")
        return ""

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        print(f"pipe:{__name__}")

        intention_response = self.determine_intention(user_message)
        print(intention_response)

        # Check intention conditions
        if 'media_chat()' in intention_response:
            self.media_chat(body, user_message)
        elif 'default_chat()' in intention_response:
            self.default_chat(body, user_message)

        # Ensure the body is a dictionary
        if isinstance(body, str):
            body = json.loads(body)

        model = body.get("model", "")
        print(f"MODEL: {model}")

        return body
