"""
title: Azure - Dall-E Manifold Pipeline
author: weisser-dev
date: 2025-03-26
version: 1.0
license: MIT
description: A pipeline for generating text and processing images using the Azure API. And including multiple Dall-e models
requirements: requests, os
environment_variables: AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_VERSION, AZURE_OPENAI_MODELS, AZURE_OPENAI_MODEL_NAMES, IMAGE_SIZE, NUM_IMAGES 
"""
from typing import List, Union, Generator, Iterator
from pydantic import BaseModel
import requests
import os

class Pipeline:
    class Valves(BaseModel):
        AZURE_OPENAI_API_KEY: str
        AZURE_OPENAI_ENDPOINT: str
        AZURE_OPENAI_API_VERSION: str
        AZURE_OPENAI_MODELS: str
        AZURE_OPENAI_MODEL_NAMES: str
        IMAGE_SIZE: str = "1024x1024"
        NUM_IMAGES: int = 1
    
    def __init__(self):
        self.type = "manifold"
        self.name = "Azure DALL·E: "
        self.valves = self.Valves(
            **{
                "AZURE_OPENAI_API_KEY": os.getenv("AZURE_OPENAI_API_KEY", "your-azure-openai-api-key-here"),
                "AZURE_OPENAI_ENDPOINT": os.getenv("AZURE_OPENAI_ENDPOINT", "your-azure-openai-endpoint-here"),
                "AZURE_OPENAI_API_VERSION": os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
                "AZURE_OPENAI_MODELS": os.getenv("AZURE_OPENAI_MODELS", "dall-e-2;dall-e-3"), #ensure that the model here is within your enpoint url, sometime the name within the url it is also like Dalle3
                "AZURE_OPENAI_MODEL_NAMES": os.getenv("AZURE_OPENAI_MODEL_NAMES", "DALL-E 2;DALL-E 3"),
            }
        )
        self.set_pipelines()
    
    def set_pipelines(self):
        models = self.valves.AZURE_OPENAI_MODELS.split(";")
        model_names = self.valves.AZURE_OPENAI_MODEL_NAMES.split(";")
        self.pipelines = [
            {"id": model, "name": name} for model, name in zip(models, model_names)
        ]
        print(f"azure_dalle_pipeline - models: {self.pipelines}")
    
    async def on_startup(self) -> None:
        print(f"on_startup:{__name__}")
    
    async def on_shutdown(self):
        print(f"on_shutdown:{__name__}")
    
    async def on_valves_updated(self):
        print(f"on_valves_updated:{__name__}")
        self.set_pipelines()
    
    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        print(f"pipe:{__name__}")

        headers = {
            "api-key": self.valves.AZURE_OPENAI_API_KEY,
            "Content-Type": "application/json",
        }
        
        url = f"{self.valves.AZURE_OPENAI_ENDPOINT}/openai/deployments/{model_id}/images/generations?api-version={self.valves.AZURE_OPENAI_API_VERSION}"
        
        payload = {
            "model": model_id,
            "prompt": user_message,
            "size": self.valves.IMAGE_SIZE,
            "n": self.valves.NUM_IMAGES,
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            message = ""
            for image in data.get("data", []):
                if "url" in image:
                    message += f"![image]({image['url']})\n"
            
            yield message
        except Exception as e:
            yield f"Error: {e} ({response.text if response else 'No response'})"
