from typing import List, Optional
from pydantic import BaseModel
import json
import aiohttp
from utils.pipelines.main import get_last_user_message

class Pipeline:
    class Valves(BaseModel):
        pipelines: List[str] = []
        priority: int = 0
        openai_base_url: str = "http://host.docker.internal:3000/v1"  # OpenAI Compatible URL

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

    # Define functions for decision/intent here
    async def process_image_ollama(self, body: dict, content: str):
        messages = body.get("messages", [])
        images = []
        for message in messages:
            if "images" in message:
                print('RUNNING PROCESS IMAGE')
                images.extend(message["images"])
                #url = f"{self.valves.openai_base_url}/chat/completions"
                url = "http://host.docker.internal:11434/api/chat" # Using ollama endpoint here because the openai ollama api doesn't yet support vision

                payload = {
                    "model": "llava:latest",
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
                            raw_llava_response = "".join(content)
                            print(raw_llava_response)
                            llava_response = f"REPEAT THIS BACK: {raw_llava_response}"
                            print(llava_response)
                            message["content"] = llava_response
                            message.pop("images", None)  # This will safely remove the 'images' key if it exists
    
    async def process_image_openai(self, body: dict, content: str):
        messages = body.get("messages", [])
        images = []
        for message in messages:
            if "images" in message:
                print('RUNNING PROCESS IMAGE')
                images.extend(message["images"])
                print(images)
                # url = f"{self.valves.openai_base_url}/chat/completions"
                url = "http://host.docker.internal:11434/api/chat" # Using ollama endpoint here because the openai ollama api doesn't yet support vision
                payload = {
                    "model": "llava:latest",
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
                            response_data = await response.json()
                            choices = response_data.get('choices', [])
                            if choices:
                                assistant_message = choices[0].get('message', {}).get('content', '')
                                print(assistant_message)
                                llava_response = f"REPEAT THIS BACK: {assistant_message}"
                                print(llava_response)
                                message["content"] = llava_response
                                message.pop("images", None)  # This will safely remove the 'images' key if it exists


    # Implement task llm to call for other models in the inlet
    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        print(f"pipe:{__name__}")

        # Ensure the body is a dictionary
        if isinstance(body, str):
            body = json.loads(body)

        model = body.get("model", "")
        user_message = get_last_user_message(body["messages"])

        # Dictionary to map intents to their corresponding functions
        model_functions = {
            'process an image using Ollama': self.process_image_ollama,
            'process an image using OpenAI': self.process_image_openai
        }

        # Function to route to the appropriate model
        async def model_router(model_to_load, body, user_message):
            # Get the function from the dictionary, defaulting to a lambda for the default case
            model_function = model_functions.get(model_to_load)
            if model_function:
                await model_function(body, user_message)
            else:
                print("Using current user-selected model")

        # Example usage - We will constrain task llm to this output - Don't know how yet
        # TODO: Determine best 1-3b param model to determine intent
        # TODO: Determine best way to constrain model output (thinking langchain OllamaFunctions? Will this work with openai endpoints?)
        #       Instruct models may just be able to be constrained reliably by the prompt
        # TODO: Implement mechanism (likely before inlet) to allow the LLM to make decision. Likely this will look like a function that
        #       takes a string and given a matching string executes correcsponding function based on model_functions dictionary
        await model_router('process an image using Ollama', body, user_message)

        # TODO: Decision - Do we want to leave state as is for ollama functions or do we want to always reload the original submittin
        #                  model? Not sure yet, but probs leave state as is.
        return body