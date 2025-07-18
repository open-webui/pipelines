"""
title: OCI Manifold Pipeline
author: felipe garcia
date: 2025-07-18
version: 1.0
license: MIT
description: A pipeline for generating text and processing images using the OCI Generative AI API.
requirements: oci
environment_variables: OCI_COMPARTMENT_ID, OCI_CONFIG_PROFILE, OCI_CONFIG_FILE, OCI_ENDPOINT
"""

import os
from typing import List, Union, Generator, Iterator
from pydantic import BaseModel
import oci
import json
from utils.pipelines.main import pop_system_message


class Pipeline:
    class Valves(BaseModel):
        OCI_COMPARTMENT_ID: str = ""
        OCI_CONFIG_PROFILE: str = ""
        OCI_CONFIG_FILE: str = ""
        OCI_ENDPOINT: str = ""

    def __init__(self):
        self.type = "manifold"
        self.id = "oci"
        self.name = "oci/"

        self.valves = self.Valves(
            **{
                "OCI_COMPARTMENT_ID": os.getenv(
                    "OCI_COMPARTMENT_ID", "your-compartment-id-here"
                ),
                "OCI_CONFIG_PROFILE": os.getenv(
                    "OCI_CONFIG_PROFILE", "DEFAULT"
                ),
                "OCI_CONFIG_FILE": os.getenv(
                    "OCI_CONFIG_FILE", "~/.oci/config"
                ),
                "OCI_ENDPOINT": os.getenv(
                    "OCI_ENDPOINT", "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com"
                ),
            }
        )

        self.update_pipelines()

    def update_pipelines(self):
        try:
            # Expand the tilde in the config file path
            config_file = os.path.expanduser(self.valves.OCI_CONFIG_FILE)
            self.config = oci.config.from_file(config_file, self.valves.OCI_CONFIG_PROFILE)
            self.generative_ai_inference_client = oci.generative_ai_inference.GenerativeAiInferenceClient(
                config=self.config, 
                service_endpoint=self.valves.OCI_ENDPOINT, 
                retry_strategy=oci.retry.NoneRetryStrategy(), 
                timeout=(10,240)
            )
            self.generative_ai_client = oci.generative_ai.GenerativeAiClient(self.config)
        except Exception as e:
            print(f"Error initializing OCI client: {e}")


    def get_models(self):
        try:
            oci_models = self.generative_ai_client.list_models(self.valves.OCI_COMPARTMENT_ID)
            models = []

            for oci_model in oci_models.data.items:
                # Filter for implemented models from xai or meta vendors
                if (oci_model.lifecycle_state == "ACTIVE" and 
                    hasattr(oci_model, 'vendor') and 
                    oci_model.vendor in ["xai", "meta"]):
                    models.append({'id': oci_model.id, 'name': oci_model.display_name})
            
            return models
        except Exception as e:
            print(f"Error getting models: {e}")
            # Return some default models if the API call fails

    async def on_startup(self):
        print(f"on_startup:{__name__}")
        pass

    async def on_shutdown(self):
        print(f"on_shutdown:{__name__}")
        pass

    async def on_valves_updated(self):
        self.update_pipelines()

    def pipelines(self) -> List[dict]:
        return self.get_models()

    def process_image(self, image_data):
        if image_data["url"].startswith("data:image"):
            mime_type, base64_data = image_data["url"].split(",", 1)
            media_type = mime_type.split(":")[1].split(";")[0]
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64_data,
                },
            }
        else:
            return {
                "type": "image",
                "source": {"type": "url", "url": image_data["url"]},
            }

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        print(f"pipe:{__name__}")

        try:
            # Remove unnecessary keys
            for key in ["user", "chat_id", "title"]:
                body.pop(key, None)

            system_message, messages = pop_system_message(messages)
            print(f"pop_system_message: {json.dumps(messages)}")
            processed_messages = []
            image_count = 0
            total_image_size = 0

            for message in messages:
                processed_content = []
                if isinstance(message.get("content"), list):
                    for item in message["content"]:
                        if item["type"] == "text":
                            processed_content.append(
                                {"type": "text", "text": item["text"]}
                            )
                        elif item["type"] == "image_url":
                            if image_count >= 5:
                                raise ValueError(
                                    "Maximum of 5 images per API call exceeded"
                                )

                            processed_image = self.process_image(item["image_url"])
                            processed_content.append(processed_image)

                            if processed_image["source"]["type"] == "base64":
                                image_size = (
                                    len(processed_image["source"]["data"]) * 3 / 4
                                )
                            else:
                                image_size = 0

                            total_image_size += image_size
                            if total_image_size > 100 * 1024 * 1024:
                                raise ValueError(
                                    "Total size of images exceeds 100 MB limit"
                                )

                            image_count += 1
                else:
                    processed_content = [
                        {"type": "text", "text": message.get("content", "")}
                    ]

                processed_messages.append(
                    {"role": message["role"], "content": processed_content}
                )

            # Prepare the payload
            payload = {
                "model_id": model_id,
                "messages": processed_messages,
                "max_tokens": body.get("max_tokens", 4096),
                "temperature": body.get("temperature", 0.8),
                "top_k": body.get("top_k", 40),
                "top_p": body.get("top_p", 0.9),
                "frequency_penalty": body.get("frequency_penalty", 0),
                "presence_penalty": body.get("presence_penalty", 0)
            }

            if body.get("stream", False):
                return self.stream_response(payload)
            else:
                return self.get_completion(payload)
        except Exception as e:
            return f"Error: {e}"

    def stream_response(self, payload: dict) -> Generator:
        """Used for title and tag generation"""
        try:
            chat_detail = oci.generative_ai_inference.models.ChatDetails()

            # Convert messages to proper format for OCI
            oci_messages = []
            for msg in payload.get("messages", []):
                oci_message = oci.generative_ai_inference.models.Message()
                oci_message.role = msg["role"].upper()
                
                content_list = []
                for content_item in msg["content"]:
                    if content_item["type"] == "text":
                        text_content = oci.generative_ai_inference.models.TextContent()
                        text_content.text = content_item["text"]
                        content_list.append(text_content)
                    elif content_item["type"] == "image":
                        # Handle image content if needed
                        pass
                
                oci_message.content = content_list
                oci_messages.append(oci_message)

            chat_request = oci.generative_ai_inference.models.GenericChatRequest()
            chat_request.api_format = oci.generative_ai_inference.models.BaseChatRequest.API_FORMAT_GENERIC
            chat_request.messages = oci_messages
            chat_request.max_tokens = payload.get("max_tokens", 4096)
            chat_request.temperature = payload.get("temperature", 0.8)
            chat_request.frequency_penalty = payload.get("frequency_penalty", 0)
            chat_request.presence_penalty = payload.get("presence_penalty", 0)
            chat_request.top_p = payload.get("top_p", 1)
            chat_request.top_k = payload.get("top_k", 0)

            chat_detail.serving_mode = oci.generative_ai_inference.models.OnDemandServingMode(model_id=payload.get("model_id"))
            chat_detail.chat_request = chat_request
            chat_detail.compartment_id = self.valves.OCI_COMPARTMENT_ID
            chat_response = self.generative_ai_inference_client.chat(chat_detail)
            
            yield chat_response.data.chat_response.choices[0].message.content[0].text
            
        except Exception as e:
            yield f"Error: {str(e)}"

    def get_completion(self, payload: dict) -> str:
        try:
            chat_detail = oci.generative_ai_inference.models.ChatDetails()

            # Convert messages to proper format for OCI
            oci_messages = []
            for msg in payload.get("messages", []):
                oci_message = oci.generative_ai_inference.models.Message()
                oci_message.role = msg["role"].upper()
                
                content_list = []
                for content_item in msg["content"]:
                    if content_item["type"] == "text":
                        text_content = oci.generative_ai_inference.models.TextContent()
                        text_content.text = content_item["text"]
                        content_list.append(text_content)
                    elif content_item["type"] == "image":
                        # Handle image content if needed
                        pass
                
                oci_message.content = content_list
                oci_messages.append(oci_message)

            chat_request = oci.generative_ai_inference.models.GenericChatRequest()
            chat_request.api_format = oci.generative_ai_inference.models.BaseChatRequest.API_FORMAT_GENERIC
            chat_request.messages = oci_messages
            chat_request.max_tokens = payload.get("max_tokens", 4096)
            chat_request.temperature = payload.get("temperature", 0.8)
            chat_request.frequency_penalty = payload.get("frequency_penalty", 0)
            chat_request.presence_penalty = payload.get("presence_penalty", 0)
            chat_request.top_p = payload.get("top_p", 1)
            chat_request.top_k = payload.get("top_k", 0)

            chat_detail.serving_mode = oci.generative_ai_inference.models.OnDemandServingMode(model_id=payload.get("model_id"))
            chat_detail.chat_request = chat_request
            chat_detail.compartment_id = self.valves.OCI_COMPARTMENT_ID

            chat_response = self.generative_ai_inference_client.chat(chat_detail)
            return chat_response.data.chat_response.choices[0].message.content[0].text
            
        except Exception as e:
            return f"Error: {str(e)}"
