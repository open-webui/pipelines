import os
import logging
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from pydantic import BaseModel, ValidationError, validator
from typing import List, Any, Union, Dict
from pipelines.function_calling_blueprint import Pipeline as FunctionCallingBlueprint

logging.basicConfig(level=logging.INFO)

"""
title: Slack Pipe Pipeline
author: Your Name
date: 2024-06-06
version: 1.0
license: MIT
description: A pipe pipeline for interacting with Slack using Open WebUI.
requirements: slack_sdk, pydantic
"""

class SlackPipePipeline(FunctionCallingBlueprint):
    class Valves(FunctionCallingBlueprint.Valves):
        pipelines: List[str] = ["*"]
        priority: int = 1

    class InputData(BaseModel):
        action: str
        channel: str = ""
        message: str = ""
        
        @validator('action')
        def validate_action(cls, v):
            valid_actions = {"send_message", "read_messages"}
            if v not in valid_actions:
                raise ValueError(f"Invalid action. Valid actions are: {valid_actions}")
            return v

    def __init__(self):
        super().__init__()
        self.name = "Slack Pipe Pipeline"
        self.valves = self.Valves(
            **{
                **self.valves.model_dump(),
                "pipelines": ["*"],  # Connect to all pipelines
            },
        )
        self.client = WebClient(token=os.getenv("xapp-1-A075PQGFRL7-7210876619108-9fa6722933215423d42aa199312e2c0a51ab07eaf01c5b1c10ab265b00534fca"))

    def process(self, data: Dict[str, Any]) -> Union[List[str], str, dict]:
        """
        Process the incoming data through the pipe pipeline.

        :param data: The incoming data to process
        :type data: Dict[str, Any]
        :return: Processed data
        :rtype: Union[List[str], str, dict]
        """
        try:
            input_data = self.InputData(**data)
            action = input_data.action
            channel = input_data.channel
            message = input_data.message

            if action == "send_message":
                return self.send_message(channel, message)
            elif action == "read_messages":
                return self.read_messages(channel)
            else:
                return {"error": "Unknown action"}
        except ValidationError as e:
            logging.error(f"Validation error: {e}")
            return {"error": f"Validation error: {e}"}
        except Exception as e:
            logging.error(f"Error processing data: {e}")
            return {"error": f"Exception occurred: {e}"}

    def send_message(self, channel: str, message: str) -> str:
        """
        Send a message to a Slack channel.
        
        :param channel: Channel ID to send the message to
        :type channel: str
        :param message: Message to send
        :type message: str
        :return: Status message
        :rtype: str
        """
        try:
            self.client.chat_postMessage(channel=channel, text=message)
            logging.info(f"Message sent to {channel}: {message}")
            return f"Message sent to {channel}: {message}"
        except SlackApiError as e:
            logging.error(f"Error sending message: {e.response['error']}")
            return f"Error sending message: {e.response['error']}"

    def read_messages(self, channel: str) -> List[str]:
        """
        Read messages from a Slack channel.
        
        :param channel: Channel ID to read messages from
        :type channel: str
        :return: List of messages
        :rtype: List[str]
        """
        try:
            response = self.client.conversations_history(channel=channel)
            messages = [msg['text'] for msg in response['messages']]
            logging.info(f"Read messages from {channel}")
            return messages
        except SlackApiError as e:
            logging.error(f"Error reading messages: {e.response['error']}")
            return [f"Error reading messages: {e.response['error']}"]

    def __call__(self, **kwargs) -> Any:
        """
        Call the pipeline with the provided arguments.

        :param kwargs: Keyword arguments
        :return: Result of the pipeline processing
        :rtype: Any
        """
        return self.process(kwargs)

if __name__ == "__main__":
    # Example usage
    slack_pipeline = SlackPipePipeline()

    # Send a message to a channel
    print(slack_pipeline({"action": "send_message", "channel": "C12345678", "message": "Hello, Slack!"}))

    # Read messages from a channel
    print(slack_pipeline({"action": "read_messages", "channel": "C12345678"}))
