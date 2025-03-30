"""
title: Langgraph stream integration
author: bartonzzx
author_url: https://github.com/bartonzzx
git_url: 
description: Integrate langgraph with open webui pipeline
required_open_webui_version: 0.4.3
requirements: none
version: 0.4.3
licence: MIT
"""


import os
import requests
from pydantic import BaseModel, Field
from typing import List, Union, Generator, Iterator


class Pipeline:
    class Valves(BaseModel):
        API_URL: str = Field(default="http://127.0.0.1:9000/stream", description="Langgraph API URL")
    
    def __init__(self):
        self.id = "LangGraph stream"
        self.name = "LangGraph stream"
        # Initialize valve paramaters
        self.valves = self.Valves(
            **{k: os.getenv(k, v.default) for k, v in self.Valves.model_fields.items()}
        )

    async def on_startup(self):
        # This function is called when the server is started.
        print(f"on_startup: {__name__}")
        pass
    
    async def on_shutdown(self): 
        # This function is called when the server is shutdown.
        print(f"on_shutdown: {__name__}")
        pass

    def pipe(
        self, 
        user_message: str, 
        model_id: str, 
        messages: List[dict], 
        body: dict
            ) -> Union[str, Generator, Iterator]:

        data = {
            "messages": [[msg['role'], msg['content']] for msg  in messages],
            }
        
        headers = {
            'accept': 'text/event-stream',
            'Content-Type': 'application/json',
        }
        
        response = requests.post(self.valves.API_URL, json=data, headers=headers, stream=True)
        
        response.raise_for_status()
        
        return response.iter_lines()