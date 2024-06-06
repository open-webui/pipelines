import os
import logging
from blueprints.function_calling_blueprint import Pipeline as FunctionCallingBlueprint
from pydantic import BaseModel, ValidationError, validator
from typing import List, Any, Union, Dict

# Ensure LinkStationPipeline is available
from linkstation_pipeline import Pipeline as LinkStationPipeline

logging.basicConfig(level=logging.INFO)

"""
title: LinkStation Pipe Pipeline
author: Your Name
date: 2024-06-06
version: 1.0
license: MIT
description: A pipeline for interacting with LinkStation using Open WebUI.
requirements: smbprotocol, pydantic
"""

class PipePipeline(FunctionCallingBlueprint):
    class Valves(FunctionCallingBlueprint.Valves):
        pipelines: List[str] = ["*"]
        priority: int = 1

    class InputData(BaseModel):
        action: str
        path: str = ""
        content: str = ""
        
        @validator('action')
        def validate_action(cls, v):
            if v not in {"list_files", "read_file", "write_file", "connect", "disconnect"}:
                raise ValueError("Invalid action")
            return v

    def __init__(self):
        super().__init__()
        self.name = "LinkStation Pipe Pipeline"
        self.valves = self.Valves(
            **{
                **self.valves.model_dump(),
                "pipelines": ["*"],  # Connect to all pipelines
            },
        )
        self.linkstation_tools = LinkStationPipeline().tools

        # Ensure necessary environment variables are set
        self.check_environment_variables()

    def check_environment_variables(self):
        required_vars = ["LINKSTATION_SERVER", "LINKSTATION_SHARE", "LINKSTATION_USERNAME", "LINKSTATION_PASSWORD"]
        for var in required_vars:
            if not os.getenv(var):
                raise EnvironmentError(f"Environment variable {var} is not set")

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
            path = input_data.path
            content = input_data.content

            if action == "list_files":
                return self.linkstation_tools.list_files(path)
            elif action == "read_file":
                return self.linkstation_tools.read_file(path)
            elif action == "write_file":
                return self.linkstation_tools.write_file(path, content)
            elif action == "connect":
                return self.linkstation_tools.connect()
            elif action == "disconnect":
                return self.linkstation_tools.disconnect()
            else:
                return {"error": "Unknown action"}
        except ValidationError as e:
            logging.error(f"Validation error: {e}")
            return {"error": f"Validation error: {e}"}
        except Exception as e:
            logging.error(f"Error processing data: {e}")
            return {"error": f"Exception occurred: {e}"}

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
    pipe_pipeline = PipePipeline()

    # Connect to LinkStation
    print(pipe_pipeline({"action": "connect"}))

    # List files in the root directory
    print(pipe_pipeline({"action": "list_files", "path": "/"}))

    # Read a file
    print(pipe_pipeline({"action": "read_file", "path": "/example.txt"}))

    # Write to a file
    print(pipe_pipeline({"action": "write_file", "path": "/example.txt", "content": "Hello, world!"}))

    # Disconnect from LinkStation
    print(pipe_pipeline({"action": "disconnect"}))
