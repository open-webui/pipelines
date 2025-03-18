"""
title: Langgraph stream integration
author: bartonzzx
author_url: https://github.com/bartonzzx
git_url: 
description: Integrate langgraph with open webui pipeline
required_open_webui_version: 0.4.3
requirements: none
version: 0.4.3
licence: MIT
"""


import os
import json
import getpass
from typing import Annotated, Literal
from typing_extensions import TypedDict

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI
from langgraph.config import get_stream_writer


'''
Define LLM API key
'''
def _set_env(var: str):
    if not os.environ.get(var):
        os.environ[var] = getpass.getpass(f"{var}: ")


_set_env("OPENAI_API_KEY")


'''
Define Langgraph
'''
def generate_custom_stream(type: Literal["think","normal"], content: str):
    content = "\n"+content+"\n"
    custom_stream_writer = get_stream_writer()
    return custom_stream_writer({type:content})

class State(TypedDict):
    messages: Annotated[list, add_messages]

llm = ChatOpenAI(model="gpt-3.5-turbo")

def chatbot(state: State):
    think_response = llm.invoke(["Please reasoning:"] + state["messages"])
    normal_response = llm.invoke(state["messages"])
    generate_custom_stream("think", think_response.content)
    generate_custom_stream("normal", normal_response.content)
    return {"messages": [normal_response]}

# Define graph
graph_builder = StateGraph(State)   

# Define nodes
graph_builder.add_node("chatbot", chatbot)
graph_builder.add_edge("chatbot", END)

# Define edges
graph_builder.add_edge(START, "chatbot")

# Compile graph
graph = graph_builder.compile()


'''
Define api processing 
'''
app = FastAPI(
    title="Langgraph API",
    description="Langgraph API",
    )

@app.get("/test")
async def test():
    return {"message": "Hello World"}


@app.post("/stream")
async def stream(inputs: State):
    async def event_stream():
        try:
            stream_start_msg = {
                'choices': 
                    [
                        {
                            'delta': {}, 
                            'finish_reason': None
                        }
                    ]
                }

            # Stream start
            yield f"data: {json.dumps(stream_start_msg)}\n\n"            

            # Processing langgraph stream response with <think> block support
            async for event in graph.astream(input=inputs, stream_mode="custom"):
                print(event)
                think_content = event.get("think", None)
                normal_content = event.get("normal", None)
    
                think_msg = {
                    'choices': 
                    [
                        {
                            'delta':
                            {
                                'reasoning_content': think_content, 
                            },
                            'finish_reason': None                            
                        }
                    ]
                }

                normal_msg = {
                    'choices': 
                    [
                        {
                            'delta':
                            {
                                'content': normal_content, 
                            },
                            'finish_reason': None                            
                        }
                    ]
                }

                yield f"data: {json.dumps(think_msg)}\n\n"
                yield f"data: {json.dumps(normal_msg)}\n\n"

            # End of the stream
            stream_end_msg = {
                'choices': [ 
                    {
                        'delta': {}, 
                        'finish_reason': 'stop'
                    }
                ]
            }
            yield f"data: {json.dumps(stream_end_msg)}\n\n"

        except Exception as e:
            # Simply print the error information
            print(f"An error occurred: {e}")

    return StreamingResponse(
        event_stream(), 
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=9000)