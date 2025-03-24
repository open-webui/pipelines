"""
title: AWS Bedrock DeepSeek Pipeline
author: kikumoto
date: 2025-03-17
version: 1.0
license: MIT
description: A pipeline for generating text using the AWS Bedrock API.
requirements: boto3
environment_variables: 
"""

import json
import logging

from typing import List, Union, Generator, Iterator, Dict, Optional, Any

import boto3

from pydantic import BaseModel

import os

from utils.pipelines.main import pop_system_message

class Pipeline:
    class Valves(BaseModel):
        AWS_ACCESS_KEY: Optional[str] = None
        AWS_SECRET_KEY: Optional[str] = None
        AWS_REGION_NAME: Optional[str] = None

    def __init__(self):
        self.type = "manifold"
        self.name = "Bedrock DeepSeek: "

        self.valves = self.Valves(
            **{
                "AWS_ACCESS_KEY": os.getenv("AWS_ACCESS_KEY", ""),
                "AWS_SECRET_KEY": os.getenv("AWS_SECRET_KEY", ""),
                "AWS_REGION_NAME": os.getenv(
                    "AWS_REGION_NAME", os.getenv(
                        "AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "")
                    )
                ),
            }
        )

        self.update_pipelines()

    async def on_startup(self):
        # This function is called when the server is started.
        print(f"on_startup:{__name__}")
        self.update_pipelines()
        pass

    async def on_shutdown(self):
        # This function is called when the server is stopped.
        print(f"on_shutdown:{__name__}")
        pass

    async def on_valves_updated(self):
        # This function is called when the valves are updated.
        print(f"on_valves_updated:{__name__}")
        self.update_pipelines()

    def update_pipelines(self) -> None:
        try:
            self.bedrock = boto3.client(service_name="bedrock",
                                        aws_access_key_id=self.valves.AWS_ACCESS_KEY,
                                        aws_secret_access_key=self.valves.AWS_SECRET_KEY,
                                        region_name=self.valves.AWS_REGION_NAME)
            self.bedrock_runtime = boto3.client(service_name="bedrock-runtime",
                                                aws_access_key_id=self.valves.AWS_ACCESS_KEY,
                                                aws_secret_access_key=self.valves.AWS_SECRET_KEY,
                                                region_name=self.valves.AWS_REGION_NAME)
            self.pipelines = self.get_models()
        except Exception as e:
            print(f"Error: {e}")
            self.pipelines = [
                {
                    "id": "error",
                    "name": "Could not fetch models from Bedrock, please set up AWS Key/Secret or Instance/Task Role.",
                },
            ]

    def pipelines(self) -> List[dict]:
        return self.get_models()

    def get_models(self):
        try:
            res = []
            response = self.bedrock.list_foundation_models(byProvider='DeepSeek')
            for model in response['modelSummaries']:
                inference_types = model.get('inferenceTypesSupported', [])
                if "ON_DEMAND" in inference_types:
                    res.append({'id': model['modelId'], 'name': model['modelName']})
                elif "INFERENCE_PROFILE" in inference_types:
                    inferenceProfileId = self.getInferenceProfileId(model['modelArn'])
                    if inferenceProfileId:
                        res.append({'id': inferenceProfileId, 'name': model['modelName']})

            return res
        except Exception as e:
            print(f"Error: {e}")
            return [
                {
                    "id": "error",
                    "name": "Could not fetch models from Bedrock, please check permissoin.",
                },
            ]

    def getInferenceProfileId(self, modelArn: str) -> str:
        response = self.bedrock.list_inference_profiles()
        for profile in response.get('inferenceProfileSummaries', []):
            for model in profile.get('models', []):
                if model.get('modelArn') == modelArn:
                    return profile['inferenceProfileId']
        return None

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        # This is where you can add your custom pipelines like RAG.
        print(f"pipe:{__name__}")

        try:
            # Remove unnecessary keys
            for key in ['user', 'chat_id', 'title']:
                body.pop(key, None)

            system_message, messages = pop_system_message(messages)

            logging.info(f"pop_system_message: {json.dumps(messages)}")

            processed_messages = []
            for message in messages:
                processed_content = []
                if isinstance(message.get("content"), list):
                    for item in message["content"]:
                        # DeepSeek currently doesn't support multi-modal inputs
                        if item["type"] == "text":
                            processed_content.append({"text": item["text"]})
                else:
                    processed_content = [{"text": message.get("content", "")}]

                processed_messages.append({"role": message["role"], "content": processed_content})

            payload = {"modelId": model_id,
                       "system": [{'text': system_message["content"] if system_message else 'you are an intelligent ai assistant'}],
                       "messages": processed_messages,
                       "inferenceConfig": {
                           "temperature": body.get("temperature", 0.5),
                           "topP": body.get("top_p", 0.9),
                           "maxTokens": body.get("max_tokens", 8192),
                           "stopSequences": body.get("stop", []),
                        },
                       }

            if body.get("stream", False):
                return self.stream_response(model_id, payload)
            else:
                return self.get_completion(model_id, payload)

        except Exception as e:
            return f"Error: {e}"

    def stream_response(self, model_id: str, payload: dict) -> Generator:
        streaming_response = self.bedrock_runtime.converse_stream(**payload)

        in_resasoning_context = False
        for chunk in streaming_response["stream"]:
            if in_resasoning_context and "contentBlockStop" in chunk:
                in_resasoning_context = False
                yield "\n </think> \n\n"
            elif "contentBlockDelta" in chunk and "delta" in chunk["contentBlockDelta"]:
                if "reasoningContent" in chunk["contentBlockDelta"]["delta"]:
                    if not in_resasoning_context:
                        yield "<think>"

                    in_resasoning_context = True
                    if "text" in chunk["contentBlockDelta"]["delta"]["reasoningContent"]:
                        yield chunk["contentBlockDelta"]["delta"]["reasoningContent"]["text"]
                elif "text" in chunk["contentBlockDelta"]["delta"]:
                    yield chunk["contentBlockDelta"]["delta"]["text"]

    def get_completion(self, model_id: str, payload: dict) -> str:
        response = self.bedrock_runtime.converse(**payload)
        return response['output']['message']['content'][0]['text']