import requests
from typing import List, Union, Generator, Iterator
try:
    from pydantic.v1 import BaseModel
except Exception:
    from pydantic import BaseModel



class Pipeline:

    class Valves(BaseModel):
        pass

    def __init__(self):
        self.id = "LangGraph Agent"
        self.name = "LangGraph Agent"

    async def on_startup(self):
        print(f"on_startup: {__name__}")
        pass

    async def on_shutdown(self):
        print(f"on_shutdown: {__name__}")
        pass

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
            ) -> Union[str, Generator, Iterator]:
        
        url = 'http://localhost:8510/openwebui-pipelines/api'
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json'
        }
        data = {
            "messages": [[msg['role'], msg['content']] for msg  in messages]
            }

        response = requests.post(url, json=data, headers=headers, stream=True)
        for line in response.iter_lines():
            if line:
                yield line.decode() + '\n'


