import os
import logging
from smbprotocol.connection import Connection
from smbprotocol.session import Session
from smbprotocol.tree import TreeConnect
from smbprotocol.open import Open
from blueprints.function_calling_blueprint import Pipeline as FunctionCallingBlueprint
from pydantic import BaseModel
from typing import List

logging.basicConfig(level=logging.INFO)

class LinkStationPipeline(FunctionCallingBlueprint):
    class Valves(FunctionCallingBlueprint.Valves):
        # Add your custom valves here
        pass

    class Tools:
        def __init__(self, pipeline) -> None:
            self.pipeline = pipeline
            self.server_name = os.getenv("LINKSTATION_SERVER", "192.168.12.34")
            self.share_name = os.getenv("LINKSTATION_SHARE", "/Open_WebUI")
            self.username = os.getenv("LINKSTATION_USERNAME", "admin")
            self.password = os.getenv("LINKSTATION_PASSWORD", "Dullownation123!")
            self.connection = None
            self.session = None
            self.tree = None
            self.connect()

        def connect(self) -> str:
            """
            Connect to the LinkStation.
            
            :return: Connection status message
            :rtype: str
            """
            try:
                self.connection = Connection(uuid.uuid4(), self.server_name)
                self.connection.connect()
                self.session = Session(self.connection, self.username, self.password)
                self.session.connect()
                self.tree = TreeConnect(self.session, self.share_name)
                self.tree.connect()
                logging.info("Connected to LinkStation successfully.")
                return "Connected to LinkStation successfully."
            except Exception as e:
                logging.error(f"Connection error: {e}")
                return f"Connection error: {e}"

        def list_files(self, path: str) -> List[str]:
            """
            List files in the specified directory.
            
            :param path: Path to the directory
            :type path: str
            :return: List of filenames
            :rtype: list[str]
            """
            try:
                directory = Open(self.tree, path)
                directory.create()
                files = directory.query_directory("*")
                directory.close()
                return [file.file_name for file in files]
            except Exception as e:
                logging.error(f"Error listing files: {e}")
                return [f"Error listing files: {e}"]

        def read_file(self, path: str) -> str:
            """
            Read the content of the specified file.
            
            :param path: Path to the file
            :type path: str
            :return: File content
            :rtype: str
            """
            try:
                file = Open(self.tree, path)
                file.create()
                file_content = file.read(0, file.end_of_file)
                file.close()
                return file_content.decode()
            except Exception as e:
                logging.error(f"Error reading file: {e}")
                return f"Error reading file: {e}"

        def write_file(self, path: str, content: str) -> str:
            """
            Write content to the specified file.
            
            :param path: Path to the file
            :type path: str
            :param content: Content to write
            :type content: str
            :return: Write status message
            :rtype: str
            """
            try:
                file = Open(self.tree, path)
                file.create(overwrite=True)
                file.write(0, content.encode())
                file.close()
                logging.info(f"File written successfully to {path}.")
                return f"File written successfully to {path}."
            except Exception as e:
                logging.error(f"Error writing file: {e}")
                return f"Error writing file: {e}"

        def disconnect(self) -> str:
            """
            Disconnect from the LinkStation.
            
            :return: Disconnection status message
            :rtype: str
            """
            try:
                if self.tree:
                    self.tree.disconnect()
                if self.session:
                    self.session.disconnect()
                if self.connection:
                    self.connection.disconnect()
                logging.info("Disconnected from LinkStation successfully.")
                return "Disconnected from LinkStation successfully."
            except Exception as e:
                logging.error(f"Disconnection error: {e}")
                return f"Disconnection error: {e}"

    def __init__(self):
        super().__init__()

        # Optionally, you can set the id and name of the pipeline.
        # Best practice is to not specify the id so that it can be automatically inferred from the filename, so that users can install multiple versions of the same pipeline.
        # The identifier must be unique across all pipelines.
        # The identifier must be an alphanumeric string that can include underscores or hyphens. It cannot contain spaces, special characters, slashes, or backslashes.
        # self.id = "my_tools_pipeline"
        self.name = "LinkStation Tools Pipeline"
        self.valves = self.Valves(
            **{
                **self.valves.model_dump(),
                "pipelines": ["*"],  # Connect to all pipelines
            },
        )
        self.tools = self.Tools(self)
