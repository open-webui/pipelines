"""
title: FlowiseAI Integration
author: Claude
author_url: https://anthropic.com
git_url: https://github.com/open-webui/pipelines/
description: Access FlowiseAI endpoints with customizable flows
required_open_webui_version: 0.4.3
requirements: requests
version: 0.4.3
licence: MIT
"""

from typing import List, Union, Generator, Iterator, Dict, Optional
from pydantic import BaseModel, Field
import requests
import os
import re
import json
from datetime import datetime
import time

from logging import getLogger
logger = getLogger(__name__)
logger.setLevel("DEBUG")


class Pipeline:
    class Valves(BaseModel):
        API_KEY: str = Field(default="", description="FlowiseAI API key")
        API_URL: str = Field(default="", description="FlowiseAI base URL")
        RATE_LIMIT: int = Field(default=5, description="Rate limit for the pipeline")
 
        FLOW_0_ENABLED: Optional[bool] = Field(default=False, description="Flow 0 Enabled (make this flow available for use)")
        FLOW_0_ID: Optional[str] = Field(default=None, description="Flow 0 ID (the FlowiseAI flow identifier)")
        FLOW_0_NAME: Optional[str] = Field(default=None, description="Flow 0 Name (human-readable name for the flow)")

        FLOW_1_ENABLED: Optional[bool] = Field(default=False, description="Flow 1 Enabled (make this flow available for use)")
        FLOW_1_ID: Optional[str] = Field(default=None, description="Flow 1 ID (the FlowiseAI flow identifier)")
        FLOW_1_NAME: Optional[str] = Field(default=None, description="Flow 1 Name (human-readable name for the flow)")

        FLOW_2_ENABLED: Optional[bool] = Field(default=False, description="Flow 2 Enabled (make this flow available for use)")
        FLOW_2_ID: Optional[str] = Field(default=None, description="Flow 2 ID (the FlowiseAI flow identifier)")
        FLOW_2_NAME: Optional[str] = Field(default=None, description="Flow 2 Name (human-readable name for the flow)")

        FLOW_3_ENABLED: Optional[bool] = Field(default=False, description="Flow 3 Enabled (make this flow available for use)")
        FLOW_3_ID: Optional[str] = Field(default=None, description="Flow 3 ID (the FlowiseAI flow identifier)")
        FLOW_3_NAME: Optional[str] = Field(default=None, description="Flow 3 Name (human-readable name for the flow)")
        
        FLOW_4_ENABLED: Optional[bool] = Field(default=False, description="Flow 4 Enabled (make this flow available for use)")
        FLOW_4_ID: Optional[str] = Field(default=None, description="Flow 4 ID (the FlowiseAI flow identifier)")
        FLOW_4_NAME: Optional[str] = Field(default=None, description="Flow 4 Name (human-readable name for the flow)")

    def __init__(self):
        self.name = "FlowiseAI Pipeline"

        # Initialize valve parameters from environment variables
        self.valves = self.Valves(
            **{k: os.getenv(k, v.default) for k, v in self.Valves.model_fields.items()}
        )
        
        # Build flow mapping for faster lookup
        self.flows = {}
        self.update_flows()

    def update_flows(self):
        """Update the flows dictionary based on the current valve settings"""
        self.flows = {}
        # Iterate through each flow
        for i in range(20):  # Support up to 20 flows
            enabled_name = f"FLOW_{i}_ENABLED"
            if not hasattr(self.valves, enabled_name):      # sequential numbering
                break
            enabled = getattr(self.valves, f"FLOW_{i}_ENABLED", False)
            flow_id = getattr(self.valves, f"FLOW_{i}_ID", None)
            flow_name = getattr(self.valves, f"FLOW_{i}_NAME", None)
            
            if enabled and flow_id and flow_name:
                self.flows[flow_name.lower()] = flow_id
        
        logger.info(f"Updated flows: {list(self.flows.keys())}")

    async def on_startup(self):
        """Called when the server is started"""
        logger.debug(f"on_startup:{self.name}")
        self.update_flows()

    async def on_shutdown(self):
        """Called when the server is stopped"""
        logger.debug(f"on_shutdown:{self.name}")

    async def on_valves_updated(self) -> None:
        """Called when valves are updated"""
        logger.debug(f"on_valves_updated:{self.name}")
        self.update_flows()

    def rate_check(self, dt_start: datetime) -> bool:
        """
        Check time, sleep if not enough time has passed for rate
        
        Args:
            dt_start (datetime): Start time of the operation
        Returns:
            bool: True if sleep was done
        """
        dt_end = datetime.now()
        time_diff = (dt_end - dt_start).total_seconds()
        time_buffer = (1 / self.valves.RATE_LIMIT)
        if time_diff >= time_buffer:  # no need to sleep
            return False
        time.sleep(time_buffer - time_diff)
        return True

    def parse_user_input(self, user_message: str) -> tuple[str, str]:
        """
        Parse the user message to extract flow name and query
        
        Format expected: @flow_name: query
        
        Args:
            user_message (str): User's input message
            
        Returns:
            tuple[str, str]: Flow name and query
        """
        # Match pattern @flow_name: query
        pattern = r"^@([^:]+):\s*(.+)$"
        match = re.match(pattern, user_message.strip())
        
        if not match:
            return None, user_message
        
        flow_name = match.group(1).strip().lower()
        query = match.group(2).strip()
        
        return flow_name, query

    def pipe(
        self, 
        user_message: str, 
        model_id: str, 
        messages: List[dict], 
        body: dict
    ) -> Union[str, Generator, Iterator]:
        """
        Main pipeline function. Calls a specified FlowiseAI flow with the provided query.
        
        Format expected: @flow_name: query
        If no flow is specified, a list of available flows will be returned.
        """
        logger.debug(f"pipe:{self.name}")
        
        dt_start = datetime.now()
        streaming = body.get("stream", False)
        logger.warning(f"Stream: {streaming}")
        context = ""
        
        # Check if we have valid API configuration
        if not self.valves.API_KEY or not self.valves.API_URL:
            error_msg = "FlowiseAI configuration missing. Please set API_KEY and API_URL valves."
            if streaming:
                yield error_msg
            else:
                return error_msg
        
        # Parse the user message to extract flow name and query
        flow_name, query = self.parse_user_input(user_message)
        
        # If no flow specified or invalid flow, list available flows
        if not flow_name or flow_name not in self.flows:
            available_flows = list(self.flows.keys())
            if not available_flows:
                no_flows_msg = "No flows configured. Enable at least one FLOW_X_ENABLED valve and set its ID and NAME."
                if streaming:
                    yield no_flows_msg
                else:
                    return no_flows_msg
            
            flows_list = "\n".join([f"- @{flow}" for flow in available_flows])
            help_msg = f"Please specify a flow using the format: @flow_name: your query\n\nAvailable flows:\n{flows_list}"
            
            if not flow_name:
                help_msg = "No flow specified. " + help_msg
            else:
                help_msg = f"Invalid flow '{flow_name}'. " + help_msg
                
            if streaming:
                yield help_msg
            else:
                return help_msg
        
        # Get the flow ID from the map
        flow_id = self.flows[flow_name]
        
        if streaming:
            yield from self.stream_retrieve(flow_id, flow_name, query, dt_start)
        else:
            for chunk in self.stream_retrieve(flow_id, flow_name, query, dt_start):
                context += chunk
            return context if context else "No response from FlowiseAI"

    def stream_retrieve(
            self, flow_id: str, flow_name: str, query: str, dt_start: datetime
        ) -> Generator:
        """
        Call the FlowiseAI endpoint with the specified flow ID and query.
        
        Args:
            flow_id (str): The ID of the flow to call
            flow_name (str): The name of the flow (for logging)
            query (str): The user's query
            dt_start (datetime): Start time for rate limiting
            
        Returns:
            Generator: Response chunks for streaming
        """
        if not query:
            yield "Query is empty. Please provide a question or prompt for the flow."
            return
            
        api_url = f"{self.valves.API_URL.rstrip('/')}/api/v1/prediction/{flow_id}"
        headers = {"Authorization": f"Bearer {self.valves.API_KEY}"}
        
        payload = {
            "question": query,
        }
        
        try:
            logger.info(f"Calling FlowiseAI flow '{flow_name}' with query: {query}")
            
            # Rate limiting check
            self.rate_check(dt_start)
            
            response = requests.post(api_url, headers=headers, json=payload)
            
            if response.status_code != 200:
                error_msg = f"Error from FlowiseAI: Status {response.status_code}"
                logger.error(f"{error_msg} - {response.text}")
                yield error_msg
                return
                
            try:
                result = response.json()
                
                # Format might vary based on flow configuration
                # Try common response formats
                if isinstance(result, dict):
                    if "text" in result:
                        yield result["text"]
                    elif "answer" in result:
                        yield result["answer"]
                    elif "response" in result:
                        yield result["response"]
                    elif "result" in result:
                        yield result["result"]
                    else:
                        # If no standard field found, return full JSON as string
                        yield f"```json\n{json.dumps(result, indent=2)}\n```"
                elif isinstance(result, str):
                    yield result
                else:
                    yield f"```json\n{json.dumps(result, indent=2)}\n```"
                    
            except json.JSONDecodeError:
                # If not JSON, return the raw text
                yield response.text
                
        except Exception as e:
            error_msg = f"Error calling FlowiseAI: {str(e)}"
            logger.error(error_msg)
            yield error_msg
            
        return 