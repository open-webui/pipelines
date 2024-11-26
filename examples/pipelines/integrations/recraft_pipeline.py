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
import re
from difflib import get_close_matches

class Pipeline:
    class Valves(BaseModel):
        RECRAFT_API_TOKEN: str

    def __init__(self):
        self.name = "Recraft AI Pipeline"
        self.valves = self.Valves(RECRAFT_API_TOKEN=os.getenv("RECRAFT_API_TOKEN", ""))
        self.client = None
        self.available_styles = [
            "realistic_image",
            "digital_illustration",
            "vector_illustration",
            "icon"
        ]

    async def on_startup(self):
        print(f"on_startup:{__name__}")
        self.client = OpenAI(
            base_url='https://external.api.recraft.ai/v1',
            api_key=self.valves.RECRAFT_API_TOKEN
        )

    async def on_shutdown(self):
        print(f"on_shutdown:{__name__}")

    def get_closest_style(self, input_style: str) -> str:
        # Convert input and available styles to lowercase for better matching
        input_style = input_style.lower()
        style_map = {s.lower(): s for s in self.available_styles}
        
        # Try to find close matches
        matches = get_close_matches(input_style, style_map.keys(), n=1, cutoff=0.6)
        
        if matches:
            closest = matches[0]
            print(f"Using style '{style_map[closest]}' for input '{input_style}'")
            return style_map[closest]
        return "realistic_image"  # default fallback

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        print(f"pipe:{__name__}")

        try:
            # Extract style from prompt if provided in [style] format
            style_match = re.search(r'\[(.*?)\]', user_message)
            selected_style = self.get_closest_style(style_match.group(1)) if style_match else "realistic_image"
            
            # Clean the prompt by removing the style specification
            clean_prompt = re.sub(r'\[.*?\]', '', user_message).strip()
            
            # Select model based on style
            model = 'recraft20b' if selected_style == 'icon' else 'recraftv3'
            
            response = self.client.images.generate(
                prompt=clean_prompt,
                style=selected_style,
                size='1280x1024',
                model=model,
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
