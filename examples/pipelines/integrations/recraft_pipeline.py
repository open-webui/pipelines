"""
title: Recraft AI Pipeline
author: Akatsuki.Ryu
author_url: https://github.com/akatsuki-ryu
sponsor: Digitalist Open Tech
date: 2024-11-26
version: 1.0
license: MIT
description: Integrate Recraft AI Image Generation API
requirements: pydantic, openai
"""

from typing import List, Union, Generator, Iterator
from pydantic import BaseModel
from openai import OpenAI
import os

class Pipeline:
    class Valves(BaseModel):
        RECRAFT_API_TOKEN: str

    def __init__(self):
        self.name = "Recraft AI Pipeline"
        self.valves = self.Valves(RECRAFT_API_TOKEN=os.getenv("RECRAFT_API_TOKEN", ""))
        self.client = None

    async def on_startup(self):
        print(f"on_startup:{__name__}")
        self.client = OpenAI(
            base_url='https://external.api.recraft.ai/v1',
            api_key=self.valves.RECRAFT_API_TOKEN
        )

    async def on_shutdown(self):
        print(f"on_shutdown:{__name__}")

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        print(f"pipe:{__name__}")

        try:
            response = self.client.images.generate(
                prompt=user_message,
                style='realistic_image',
                size='1280x1024',
            )
            print(response)

            if response and response.data and len(response.data) > 0:
                image_url = response.data[0].url
                message = f"![image]({image_url})\n"
                return message
            else:
                return "No image was generated in the response."

        except Exception as e:
            return f"Error generating image: {str(e)}"
