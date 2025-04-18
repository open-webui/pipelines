from typing import List, Union, Generator, Iterator, Optional
from pprint import pprint
import time

# Uncomment to disable SSL verification warnings if needed.
# warnings.filterwarnings('ignore', message='Unverified HTTPS request')


class Pipeline:
    def __init__(self):
        self.name = "Pipeline with Status Event"
        self.description = (
            "This is a pipeline that demonstrates how to use the status event."
        )
        self.debug = True
        self.version = "0.1.0"
        self.author = "Anthony Durussel"

    async def on_startup(self):
        # This function is called when the server is started.
        print(f"on_startup: {__name__}")
        pass

    async def on_shutdown(self):
        # This function is called when the server is shutdown.
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

    def pipe(
        self,
        user_message: str,
        model_id: str,
        messages: List[dict],
        body: dict,
    ) -> Union[str, Generator, Iterator]:
        print(f"pipe: {__name__}")

        if self.debug:
            print(f"pipe: {__name__} - received message from user: {user_message}")

        yield {
            "event": {
                "type": "status",
                "data": {
                    "description": "Fake Status",
                    "done": False,
                },
            }
        }

        time.sleep(5)  # Sleep for 5 seconds

        yield f"user_message: {user_message}"

        yield {
            "event": {
                "type": "status",
                "data": {
                    "description": "",
                    "done": True,
                },
            }
        }
