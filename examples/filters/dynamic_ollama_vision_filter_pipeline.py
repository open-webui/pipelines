"""
title: Ollama Dynamic Vision Pipeline
author: Andrew Tait Gehrhardt
date: 2024-06-18
version: 1.0
license: MIT
description: A pipeline for dynamically processing images when current model is a text only model
requirements: pydantic, aiohttp
"""

from typing import List, Optional
from pydantic import BaseModel
import json
import aiohttp
from utils.pipelines.main import get_last_user_message

class Pipeline:
    class Valves(BaseModel):
        pipelines: List[str] = []
        priority: int = 0
        vision_model: str = "llava"
        ollama_base_url: str = ""
        model_to_override: str = ""

    def __init__(self):
        self.type = "filter"
        self.name = "Interception Filter"
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

    async def process_images_with_llava(self, images: List[str], content: str, vision_model: str, ollama_base_url: str) -> str:
        url = f"{ollama_base_url}/api/chat"
        payload = {
            "model": vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": content,
                    "images": images
                }
            ]
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    content = []
                    async for line in response.content:
                        data = json.loads(line)
                        content.append(data.get("message", {}).get("content", ""))
                    return "".join(content)
                else:
                    print(f"Failed to process images with LLava, status code: {response.status}")
                    return ""

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        print(f"pipe:{__name__}")

        images = []

        # Ensure the body is a dictionary
        if isinstance(body, str):
            body = json.loads(body)
        
        model = body.get("model", "")

        # Get the content of the most recent message
        user_message = get_last_user_message(body["messages"])

        if model in self.valves.model_to_override:
            messages = body.get("messages", [])
            for message in messages:
                if "images" in message:
                    images.extend(message["images"])
                    raw_llava_response = await self.process_images_with_llava(images, user_message, self.valves.vision_model,self.valves.ollama_base_url)
                    llava_response = f"REPEAT THIS BACK: {raw_llava_response}"
                    message["content"] = llava_response
                    message.pop("images", None)  # This will safely remove the 'images' key if it exists
        
        return body
