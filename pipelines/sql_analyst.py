"""
title: Text to SQL Pipeline
author: open-webui
version: 1.0
license: MIT
description: A pipeline for converting natural language to SQL queries using LangChain
requirements: langchain-openai,sqlalchemy,psycopg2-binary
"""

import os
from typing import List, Union, Generator, Iterator
from pydantic import BaseModel
from sqlalchemy import create_engine
from langchain_openai import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from pipelines.text_to_sql.base import create_sql_agent
from pipelines.text_to_sql.toolkit import SQLDatabaseToolkit

class Pipeline:
    class Valves(BaseModel):
        DB_CONNECTION_STRING: str = "postgresql://user:pass@localhost:5432/db"
        OPENAI_API_KEY: str = ""
        MODEL: str = "gpt-4-turbo"

    def __init__(self):
        self.name = "Inverse Stats DB Agent"
        self.engine = None
        self.nlsql_response = ""
        self.valves = self.Valves(
            **{
                "DB_CONNECTION_STRING": os.getenv("DB_CONNECTION_STRING", "postgresql://user:pass@localhost:5432/db"),
                "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", "your-openai-api-key-here"),
                "MODEL": os.getenv("MODEL", "gpt-4-turbo")
            }
        )
        self.init_db_connection()

    def init_db_connection(self):
        self.engine = create_engine(self.valves.DB_CONNECTION_STRING)
        return self.engine

    async def on_startup(self):
        """This function is called when the server is started."""
        print(f"on_startup:{__name__}")
        self.init_db_connection()

    async def on_shutdown(self):
        """This function is called when the server is stopped."""
        print(f"on_shutdown:{__name__}")
        if self.engine:
            self.engine.dispose()

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        # Add debug prints like in OpenAI pipeline
        print(f"pipe:{__name__}")
        print(messages)
        print(user_message)

        # Check for special message types that don't need SQL
        if body.get("title", False):
            print("Title Generation")
            return "INV Price Checker"

        # Only create SQL agent for actual database queries
        llm = ChatOpenAI(
            temperature=0.1,
            model=self.valves.MODEL,
            openai_api_key=self.valves.OPENAI_API_KEY,
            streaming=True
        )

        db = SQLDatabase(self.engine)
        
        toolkit = SQLDatabaseToolkit(db=db, llm=llm)
        agent_executor = create_sql_agent(
            llm=llm,
            toolkit=toolkit,
            verbose=True,
            agent_type="openai-functions",
            max_iterations=10,
            handle_parsing_errors=True
        )

        try:
            if body.get("stream", False):
                # Collect the complete response first
                response_chunks = []
                for chunk in agent_executor.stream({"input": user_message}):
                    if isinstance(chunk, dict):
                        # Collect all relevant parts of the response
                        if "intermediate_steps" in chunk:
                            for step in chunk["intermediate_steps"]:
                                if isinstance(step, tuple) and len(step) == 2:
                                    action, output = step
                                    if output and str(output) != "None":
                                        response_chunks.append(str(output))
                        if "output" in chunk and chunk["output"]:
                            response_chunks.append(str(chunk["output"]))
                        if "content" in chunk and chunk["content"]:
                            response_chunks.append(str(chunk["content"]))

                # Process the complete response
                complete_response = "\n".join(response_chunks)
                final_response = self._process_response(complete_response)

                # Stream the final response
                if final_response:
                    for line in final_response.split('\n'):
                        yield line + "\n"
                else:
                    yield "No valid response generated. Please try rephrasing your question."
            else:
                response = agent_executor.invoke(
                    {"input": user_message},
                    {"return_only_outputs": True}
                )
                return self._process_response(str(response.get("output", "")))
        except Exception as e:
            return f"Error executing query: {str(e)}"

    def _process_response(self, response: str) -> str:
        """Process and clean the response."""
        if not response:
            return ""

        # Split into lines and process
        lines = response.split('\n')
        processed_lines = []
        
        # Track if we're inside a code block or JSON block
        in_code_block = False
        json_content = []
        
        for line in lines:
            line = line.strip()
            
            # Skip empty lines and system messages
            if not line or line.lower().startswith(('responded:', 'invoking:', '> entering', '> finished')):
                continue
                
            # Handle JSON content
            if line.startswith('{') and line.endswith('}'):
                json_content.append(line)
                continue
                
            # Handle code blocks
            if line.startswith('```'):
                in_code_block = not in_code_block
                continue
                
            if not in_code_block:
                processed_lines.append(line)
        
        # Combine processed lines
        result = '\n'.join(processed_lines)
        
        # Add JSON content at the end if present
        if json_content:
            result += '\n\n' + '\n'.join(json_content)
            
        return result.strip()