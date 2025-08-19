import argparse
import logging
import time
from typing import Union, Generator, Iterator, Optional
from pprint import pprint
import requests, json, warnings

# Langflow API Docs:
# https://docs.langflow.org/workspace-api

# Disable SSL verification warnings
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

def is_healthy(url, verify_ssl=True):
    """Check if the Langflow server is healthy."""
    try:
        response = requests.get(url, verify=verify_ssl)
        return response.status_code == 200
    except Exception as e:
        print(f"Error checking health: {str(e)}")
        return False

def get_flow_components(url, verify_ssl=True):
    """Get the flow components IDs from the Langflow server."""
    try:
        response = requests.get(url, headers={"Content-Type": "application/json"}, verify=verify_ssl)
        response.raise_for_status()
        data = response.json()
        
        # Create dictionary of component IDs with empty objects
        components = {}
        for node in data.get('data', {}).get('nodes', []):
            component_id = node.get('data', {}).get('id')
            if component_id:
                components[component_id] = {}
        
        return components
    except Exception as e:
        print(f"Error getting flow components: {str(e)}")
        return {}

class Pipeline:
    def __init__(self):
        self.name = "Langflow Chat"
        self.langflow_host = "http://langflow.host"
        self.flow_id = "28eeaa04-...-...-...-9a5f257dd17c"
        self.api_url_run = self.langflow_host+"/api/v1/run"
        self.api_url_flow = self.langflow_host+"/api/v1/flows"
        self.api_health = self.langflow_host+"/health"
        self.api_request_stream = True
        self.verify_ssl = False
        self.debug = False
        
    async def on_startup(self):
        print(f"on_startup: {__name__}")
        # Wait for Langflow server to be healthy
        healthy = is_healthy(self.api_health, self.verify_ssl)
        while not healthy:
            time.sleep(5)
            healthy = is_healthy(self.api_health)
        print("Langflow server is healthy")
        
    async def on_shutdown(self): 
        print(f"on_shutdown: {__name__}")
        pass

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        # This function is called before the OpenAI API request is made. You can modify the form data before it is sent to the OpenAI API.
        print(f"inlet: {__name__}")
        if self.debug:
            print(f"inlet: {__name__} - body:")
            pprint(body)
            print(f"inlet: {__name__} - user:")
            pprint(user)
        return body

    async def outlet(self, body: dict, user: Optional[dict] = None) -> dict:
        # This function is called after the OpenAI API response is completed. You can modify the messages after they are received from the OpenAI API.
        print(f"outlet: {__name__}")
        if self.debug:
            print(f"outlet: {__name__} - body:")
            pprint(body)
            print(f"outlet: {__name__} - user:")
            pprint(user)
        return body

    def pipe(self, user_message: str, model_id: str, messages: list, body: dict) -> Union[str, Generator, Iterator]:
        """Process the user message through the Langflow pipeline."""
        print(f"Processing message with {self.name}")
        
        if self.debug is True:
            print(f"User message: {user_message}")
            print(f"Model ID: {model_id}")
            print(f"Messages: {messages}")
            print(f"Body: {body}")

        session_id = body.get("chat_id")

        # If you need to tune components in flow / use `get_flow_components` to collect IDs
        TWEAKS_COMPONENTS = get_flow_components(url=self.api_url_flow+"/"+self.flow_id, verify_ssl=self.verify_ssl)

        data = {
            "input_value": user_message,
            "output_type": "chat",
            "input_type": "chat",
            "session_id": session_id,
            "tweaks": TWEAKS_COMPONENTS
        }
        try:
            # Make the initial request to run flow via Langflow API ChatInput box
            url = f"{self.api_url_run}/{self.flow_id}?stream={str(self.api_request_stream).lower()}"
            headers = {"Content-Type": "application/json"}
            response = requests.post(url, json=data, headers=headers, verify=self.verify_ssl)
            response.raise_for_status()
            
            if response.status_code == 200:
                init_data = response.json()
                if self.debug is True:
                    print(f"pipe: {__name__} - langflow init response: "+str(init_data))
                
                # Check for stream URL in the response
                outputs = init_data.get("outputs", [{}])[0].get("outputs", [{}])[0]
                stream_url = outputs.get("artifacts", {}).get("stream_url")
                
                if not stream_url:
                    message = outputs.get("messages", [])[0].get("message")
                    if message is not None:
                        yield message
                        return
                    logging.error("No stream URL returned")
                    yield "Error: No stream URL available"
                    return

                # Stream the response
                stream_url = f"{self.langflow_host}{stream_url}"
                params = {"session_id": session_id}
                print(f"Stream the response session_id: {session_id} - {stream_url}")
                
                with requests.get(stream_url, headers=headers, params=params, stream=True, verify=self.verify_ssl) as stream:
                    for line in stream.iter_lines(decode_unicode=True):
                        if line.startswith('data: '):
                            try:
                                # Remove 'data: ' prefix and parse JSON
                                json_data = json.loads(line.replace('data: ', ''))
                                # Extract chunk
                                if 'chunk' in json_data:
                                    yield json_data['chunk']
                                if 'message' in json_data:
                                    if json_data['message'] == 'Stream closed':
                                        print(f"Stream session {session_id} closed")
                                        return
                            except json.JSONDecodeError:
                                print(f"Failed to parse JSON: {line}")
            else:
                yield f"Error: Request failed with status code {response.status_code}"
                
        except Exception as e:
            logging.error(f"Error in pipe: {str(e)}")
            yield f"Error: {str(e)}"
