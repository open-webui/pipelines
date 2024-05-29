from typing import List, Union, Generator, Iterator
from schemas import OpenAIChatMessage
import subprocess


class Pipeline:
    def __init__(self):
        # Optionally, you can set the id and name of the pipeline.
        self.id = "python_code_pipeline"
        self.name = "Python Code Pipeline"
        pass

    async def on_startup(self):
        # This function is called when the server is started.
        print(f"on_startup:{__name__}")
        pass

    async def on_shutdown(self):
        # This function is called when the server is stopped.
        print(f"on_shutdown:{__name__}")
        pass

    def execute_python_code(self, code):
        try:
            result = subprocess.run(
                ["python", "-c", code], capture_output=True, text=True, check=True
            )
            stdout = result.stdout.strip()
            return stdout, result.returncode
        except subprocess.CalledProcessError as e:
            return e.output.strip(), e.returncode

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        # This is where you can add your custom pipelines like RAG.'
        print(f"pipe:{__name__}")

        print(messages)
        print(user_message)

        if body.get("title", False):
            print("Title Generation")
            return "Python Code Pipeline"
        else:
            stdout, return_code = self.execute_python_code(user_message)
            return stdout
