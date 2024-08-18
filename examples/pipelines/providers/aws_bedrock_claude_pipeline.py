"""
title: AWS Bedrock Claude Pipeline
author: G-mario
date: 2024-08-18
version: 1.0
license: MIT
description: A pipeline for generating text and processing images using the AWS Bedrock API(By Anthropic claude).
requirements: requests, boto3
environment_variables: AWS_ACCESS_KEY, AWS_SECRET_KEY, AWS_REGION_NAME
"""
import base64
import json
import logging
from io import BytesIO
from typing import List, Union, Generator, Iterator

import boto3

from pydantic import BaseModel

import os
import requests

from utils.pipelines.main import pop_system_message


class Pipeline:
    class Valves(BaseModel):
        AWS_ACCESS_KEY: str = ""
        AWS_SECRET_KEY: str = ""
        AWS_REGION_NAME: str = ""

    def __init__(self):
        self.type = "manifold"
        # Optionally, you can set the id and name of the pipeline.
        # Best practice is to not specify the id so that it can be automatically inferred from the filename, so that users can install multiple versions of the same pipeline.
        # The identifier must be unique across all pipelines.
        # The identifier must be an alphanumeric string that can include underscores or hyphens. It cannot contain spaces, special characters, slashes, or backslashes.
        # self.id = "openai_pipeline"
        self.name = "Bedrock: "

        self.valves = self.Valves(
            **{
                "AWS_ACCESS_KEY": os.getenv("AWS_ACCESS_KEY", "your-aws-access-key-here"),
                "AWS_SECRET_KEY": os.getenv("AWS_SECRET_KEY", "your-aws-secret-key-here"),
                "AWS_REGION_NAME": os.getenv("AWS_REGION_NAME", "your-aws-region-name-here"),
            }
        )

        self.bedrock = boto3.client(aws_access_key_id=self.valves.AWS_ACCESS_KEY,
                                    aws_secret_access_key=self.valves.AWS_SECRET_KEY,
                                    service_name="bedrock",
                                    region_name=self.valves.AWS_REGION_NAME)
        self.bedrock_runtime = boto3.client(aws_access_key_id=self.valves.AWS_ACCESS_KEY,
                                            aws_secret_access_key=self.valves.AWS_SECRET_KEY,
                                            service_name="bedrock-runtime",
                                            region_name=self.valves.AWS_REGION_NAME)

        self.pipelines = self.get_models()


    async def on_startup(self):
        # This function is called when the server is started.
        print(f"on_startup:{__name__}")
        pass

    async def on_shutdown(self):
        # This function is called when the server is stopped.
        print(f"on_shutdown:{__name__}")
        pass

    async def on_valves_updated(self):
        # This function is called when the valves are updated.
        print(f"on_valves_updated:{__name__}")
        self.bedrock = boto3.client(aws_access_key_id=self.valves.AWS_ACCESS_KEY,
                                    aws_secret_access_key=self.valves.AWS_SECRET_KEY,
                                    service_name="bedrock",
                                    region_name=self.valves.AWS_REGION_NAME)
        self.bedrock_runtime = boto3.client(aws_access_key_id=self.valves.AWS_ACCESS_KEY,
                                            aws_secret_access_key=self.valves.AWS_SECRET_KEY,
                                            service_name="bedrock-runtime",
                                            region_name=self.valves.AWS_REGION_NAME)
        self.pipelines = self.get_models()

    def pipelines(self) -> List[dict]:
        return self.get_models()

    def get_models(self):
        if self.valves.AWS_ACCESS_KEY and self.valves.AWS_SECRET_KEY:
            try:
                response = self.bedrock.list_foundation_models(byProvider='Anthropic', byInferenceType='ON_DEMAND')
                return [
                    {
                        "id": model["modelId"],
                        "name": model["modelName"],
                    }
                    for model in response["modelSummaries"]
                ]
            except Exception as e:
                print(f"Error: {e}")
                return [
                    {
                        "id": "error",
                        "name": "Could not fetch models from Bedrock, please update the Access/Secret Key in the valves.",
                    },
                ]
        else:
            return []

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        # This is where you can add your custom pipelines like RAG.
        print(f"pipe:{__name__}")

        system_message, messages = pop_system_message(messages)

        logging.info(f"pop_system_message: {json.dumps(messages)}")

        try:
            processed_messages = []
            image_count = 0
            for message in messages:
                processed_content = []
                if isinstance(message.get("content"), list):
                    for item in message["content"]:
                        if item["type"] == "text":
                            processed_content.append({"text": item["text"]})
                        elif item["type"] == "image_url":
                            if image_count >= 20:
                                raise ValueError("Maximum of 20 images per API call exceeded")
                            processed_image = self.process_image(item["image_url"])
                            processed_content.append(processed_image)
                            image_count += 1
                else:
                    processed_content = [{"text": message.get("content", "")}]

                processed_messages.append({"role": message["role"], "content": processed_content})

            payload = {"modelId": model_id,
                       "messages": processed_messages,
                       "system": [{'text': system_message if system_message else 'you are an intelligent ai assistant'}],
                       "inferenceConfig": {"temperature": body.get("temperature", 0.5)},
                       "additionalModelRequestFields": {"top_k": body.get("top_k", 200), "top_p": body.get("top_p", 0.9)}
                       }
            if body.get("stream", False):
                return self.stream_response(model_id, payload)
            else:
                return self.get_completion(model_id, payload)
        except Exception as e:
            return f"Error: {e}"

    def process_image(self, image: str):
        img_stream = None
        if image["url"].startswith("data:image"):
            if ',' in image["url"]:
                base64_string = image["url"].split(',')[1]
            image_data = base64.b64decode(base64_string)

            img_stream = BytesIO(image_data)
        else:
            img_stream = requests.get(image["url"]).content
        return {
            "image": {"format": "png" if image["url"].endswith(".png") else "jpeg",
                      "source": {"bytes": img_stream.read()}}
        }

    def stream_response(self, model_id: str, payload: dict) -> Generator:
        if "system" in payload:
            del payload["system"]
        if "additionalModelRequestFields" in payload:
            del payload["additionalModelRequestFields"]
        streaming_response = self.bedrock_runtime.converse_stream(**payload)
        for chunk in streaming_response["stream"]:
            if "contentBlockDelta" in chunk:
                yield chunk["contentBlockDelta"]["delta"]["text"]

    def get_completion(self, model_id: str, payload: dict) -> str:
        response = self.bedrock_runtime.converse(**payload)
        return response['output']['message']['content'][0]['text']

