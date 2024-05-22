from typing import List, Union, Generator, Iterator
import requests
import subprocess
import os
import socket
from schemas import OpenAIChatMessage


class Pipeline:
    def __init__(self):
        # Optionally, you can set the id and name of the pipeline.
        self.id = "mlx_pipeline"
        self.name = "MLX Pipeline"
        self.process = None
        self.model = os.getenv('MLX_MODEL', 'mistralai/Mistral-7B-Instruct-v0.2')  # Default model if not set in environment variable
        self.port = self.find_free_port()

    @staticmethod
    def find_free_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            return s.getsockname()[1]

    async def on_startup(self):
        # This function is called when the server is started.
        print(f"on_startup:{__name__}")
        self.start_subprocess()

    async def on_shutdown(self):
        # This function is called when the server is stopped.
        print(f"on_shutdown:{__name__}")
        self.stop_subprocess()

    def start_subprocess(self):
        # Start the subprocess for "mlx_lm.server --model ${MLX_MODEL} --port ${PORT}"
        try:
            self.process = subprocess.Popen(
                ["mlx_lm.server", "--model", self.model, "--port", str(self.port)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            print(f"Subprocess started with PID: {self.process.pid} on port {self.port}")
        except Exception as e:
            print(f"Failed to start subprocess: {e}")

    def stop_subprocess(self):
        # Stop the subprocess if it is running
        if self.process:
            try:
                self.process.terminate()
                self.process.wait()
                print(f"Subprocess with PID {self.process.pid} terminated")
            except Exception as e:
                print(f"Failed to terminate subprocess: {e}")

    def get_response(
        self, user_message: str, messages: List[OpenAIChatMessage], body: dict
    ) -> Union[str, Generator, Iterator]:
        # This is where you can add your custom pipelines like RAG.'
        print(f"get_response:{__name__}")

        MLX_BASE_URL = f"http://localhost:{self.port}"
        MODEL = "llama3"

        if "user" in body:
            print("######################################")
            print(f'# User: {body["user"]["name"]} ({body["user"]["id"]})')
            print(f"# Message: {user_message}")
            print("######################################")

        try:
            r = requests.post(
                url=f"{MLX_BASE_URL}/v1/chat/completions",
                json={**body, "model": MODEL},
                stream=True,
            )

            r.raise_for_status()

            if body["stream"]:
                return r.iter_lines()
            else:
                return r.json()
        except Exception as e:
            return f"Error: {e}"