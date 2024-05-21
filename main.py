from fastapi import FastAPI, Request, Depends, status
from fastapi.middleware.cors import CORSMiddleware

from starlette.responses import StreamingResponse, Response
from pydantic import BaseModel, ConfigDict
from typing import List


import time
import json
import uuid

from utils import stream_message_template
from config import MODEL_ID, MODEL_NAME


app = FastAPI(docs_url="/docs", redoc_url=None)


origins = ["*"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def check_url(request: Request, call_next):
    start_time = int(time.time())
    response = await call_next(request)
    process_time = int(time.time()) - start_time
    response.headers["X-Process-Time"] = str(process_time)

    return response


@app.get("/models")
@app.get("/v1/models")
async def get_models():
    """
    Returns the model that is available inside Dialog in the OpenAI format.
    """
    return {
        "data": [
            {
                "id": MODEL_ID,
                "name": MODEL_NAME,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "openai",
            }
        ]
    }


class OpenAIChatMessage(BaseModel):
    role: str
    content: str

    model_config = ConfigDict(extra="allow")


class OpenAIChatCompletionForm(BaseModel):
    model: str
    messages: List[OpenAIChatMessage]

    model_config = ConfigDict(extra="allow")


def get_response(user_message):
    return f"rag response to: {user_message}"


@app.post("/chat/completions")
@app.post("/v1/chat/completions")
async def generate_openai_chat_completion(form_data: OpenAIChatCompletionForm):

    # get last user message (role == 'user') from the form_data
    # last message might be role == 'assistant' or 'system' or 'user'
    user_message = form_data.messages[-1].content

    res = get_response(user_message)

    finish_message = {
        "id": f"rag-{str(uuid.uuid4())}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": MODEL_ID,
        "choices": [
            {"index": 0, "delta": {}, "logprobs": None, "finish_reason": "stop"}
        ],
    }

    def stream_content():
        message = stream_message_template(res)

        yield f"data: {json.dumps(message)}\n\n"
        yield f"data: {json.dumps(finish_message)}\n\n"
        yield f"data: [DONE]"

    return StreamingResponse(stream_content(), media_type="text/event-stream")


@app.get("/")
async def get_status():
    return {"status": True}
