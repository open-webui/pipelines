"""
title: AWS Bedrock Claude Pipeline
author: G-mario, jknapp
date: 2025-06-02
version: 1.4
license: MIT
description: A pipeline for generating text and processing images using the AWS Bedrock API(By Anthropic claude).
requirements: requests, boto3
environment_variables: AWS_ACCESS_KEY (optional with instance roles), AWS_SECRET_KEY (optional with instance roles), AWS_REGION_NAME
"""
import base64
import json
import logging
from io import BytesIO
from typing import List, Union, Generator, Iterator, Optional, Any

import boto3

from pydantic import BaseModel

import os
import requests

from utils.pipelines.main import pop_system_message

REASONING_EFFORT_BUDGET_TOKEN_MAP = {
    "none": None,
    "low": 1024,
    "medium": 4096,
    "high": 16384,
    "max": 32768,
}

# Maximum combined token limit for Claude Sonnet 3.7 and 4.0
MAX_COMBINED_TOKENS = 64000
OPUS_MAX_COMBINED_TOKENS = 32000


class Pipeline:
    class Valves(BaseModel):
        AWS_ACCESS_KEY: Optional[str] = None
        AWS_SECRET_KEY: Optional[str] = None
        AWS_REGION_NAME: Optional[str] = None

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
            # Check if we have explicit credentials or should try instance role
            if self.valves.AWS_ACCESS_KEY and self.valves.AWS_SECRET_KEY:
                # Use explicit credentials
                self.bedrock = boto3.client(
                    service_name="bedrock",
                                        aws_access_key_id=self.valves.AWS_ACCESS_KEY,
                                        aws_secret_access_key=self.valves.AWS_SECRET_KEY,
                    region_name=self.valves.AWS_REGION_NAME
                )
                self.bedrock_runtime = boto3.client(
                    service_name="bedrock-runtime",
                                                aws_access_key_id=self.valves.AWS_ACCESS_KEY,
                                                aws_secret_access_key=self.valves.AWS_SECRET_KEY,
                    region_name=self.valves.AWS_REGION_NAME
                )
                print("Using provided AWS credentials")
            else:
                # Try to use instance role
                region = self.valves.AWS_REGION_NAME if self.valves.AWS_REGION_NAME else None
                self.bedrock = boto3.client(service_name="bedrock", region_name=region)
                self.bedrock_runtime = boto3.client(service_name="bedrock-runtime", region_name=region)
                print("No AWS credentials provided, using instance role or AWS credential chain")

            self.pipelines = self.get_models()
        except Exception as e:
            print(f"Error: {e}")
            self.pipelines = [
                {
                    "id": "error",
                    "name": "Could not fetch models from Bedrock. Please check AWS credentials or instance role permissions.",
                },
            ]

    def get_models(self):
        try:
            res = []
            response = self.bedrock.list_foundation_models(byProvider='Anthropic')
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
            print(f"Error accessing Bedrock: {e}")
            return [
                {
                    "id": "error",
                    "name": "Could not fetch models from Bedrock. Please check AWS credentials or instance role permissions.",
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
                       "system": [{'text': system_message["content"] if system_message else 'you are an intelligent ai assistant'}],
                       "inferenceConfig": {
                           "temperature": body.get("temperature", 0.5),
                           "topP": body.get("top_p", 0.9),
                           "maxTokens": body.get("max_tokens", 4096),
                           "stopSequences": body.get("stop", []),
                        },
                        "additionalModelRequestFields": {"top_k": body.get("top_k", 200)}
                       }

            if body.get("stream", False):
                supports_thinking = False
                if "claude" in model_id.lower():
                    # Extract version from model_id using string operations or regex
                    import re
                    version_match = re.search(r'claude-(\d+)(?:\.(\d+))?', model_id.lower())
                    if version_match:
                        major_version = int(version_match.group(1))
                        minor_version = int(version_match.group(2)) if version_match.group(2) else 0
                        # Claude 3.7+ and Claude 4+ support thinking
                        supports_thinking = (major_version > 3) or (major_version == 3 and minor_version >= 7)
                reasoning_effort = body.get("reasoning_effort", "none")
                budget_tokens = REASONING_EFFORT_BUDGET_TOKEN_MAP.get(reasoning_effort)

                # Allow users to input an integer value representing budget tokens
                if (
                    not budget_tokens
                    and reasoning_effort not in REASONING_EFFORT_BUDGET_TOKEN_MAP.keys()
                ):
                    try:
                        budget_tokens = int(reasoning_effort)
                    except ValueError as e:
                        print("Failed to convert reasoning effort to int", e)
                        budget_tokens = None

                if supports_thinking and budget_tokens:
                    # Check if the combined tokens (budget_tokens + max_tokens) exceeds the limit
                    max_tokens = payload.get("max_tokens", 4096)
                    combined_tokens = budget_tokens + max_tokens
                    # Opus version of the model has a lower max token theshold 
                    if "opus" in model_id.lower():
                        if combined_tokens > OPUS_MAX_COMBINED_TOKENS:
                            error_message = f"Error: Combined tokens (budget_tokens {budget_tokens} + max_tokens {max_tokens} = {combined_tokens}) exceeds the maximum limit of {MAX_COMBINED_TOKENS}"
                            print(error_message)
                            return error_message
                    else:
                        if combined_tokens > MAX_COMBINED_TOKENS:
                            error_message = f"Error: Combined tokens (budget_tokens {budget_tokens} + max_tokens {max_tokens} = {combined_tokens}) exceeds the maximum limit of {MAX_COMBINED_TOKENS}"
                            print(error_message)
                            return error_message

                    payload["inferenceConfig"]["maxTokens"] = combined_tokens
                    payload["additionalModelRequestFields"]["thinking"] = {
                        "type": "enabled",
                        "budget_tokens": budget_tokens,
                    }
                    # Thinking requires temperature 1.0 and does not support top_p, top_k
                    payload["inferenceConfig"]["temperature"] = 1.0
                    if "top_k" in payload["additionalModelRequestFields"]:
                        del payload["additionalModelRequestFields"]["top_k"]
                    if "topP" in payload["inferenceConfig"]:
                        del payload["inferenceConfig"]["topP"]
                return self.stream_response(model_id, payload)
            else:
                return self.get_completion(model_id, payload)
        except Exception as e:
            return f"Error: {e}"

    def process_image(self, image: str):
        img_stream = None
        content_type = None

        if image["url"].startswith("data:image"):
            mime_type, base64_string = image["url"].split(",", 1)
            content_type = mime_type.split(":")[1].split(";")[0]
            image_data = base64.b64decode(base64_string)
            img_stream = BytesIO(image_data)
        else:
            response = requests.get(image["url"])
            img_stream = BytesIO(response.content)
            content_type = response.headers.get('Content-Type', 'image/jpeg')

        media_type = content_type.split('/')[-1] if '/' in content_type else content_type
        return {
            "image": {
                "format": media_type,
                "source": {"bytes": img_stream.read()}
            }
        }

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
