from fastapi import FastAPI, Request, Depends, status
from fastapi.middleware.cors import CORSMiddleware

from starlette.responses import StreamingResponse, Response
from pydantic import BaseModel, ConfigDict
from typing import List, Union, Generator


import time
import json
import uuid

from utils import get_last_user_message, stream_message_template
from schemas import OpenAIChatCompletionForm
from config import MODEL_ID, MODEL_NAME

from rag_pipeline import get_response

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


@app.post("/chat/completions")
@app.post("/v1/chat/completions")
async def generate_openai_chat_completion(form_data: OpenAIChatCompletionForm):
    user_message = get_last_user_message(form_data.messages)

    def stream_content():
        res = get_response(user_message, messages=form_data.messages)

        if isinstance(res, str):
            message = stream_message_template(res)
            yield f"data: {json.dumps(message)}\n\n"

        elif isinstance(res, Generator):
            for message in res:
                message = stream_message_template(message)
                yield f"data: {json.dumps(message)}\n\n"

        finish_message = {
            "id": f"rag-{str(uuid.uuid4())}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": MODEL_ID,
            "choices": [
                {"index": 0, "delta": {}, "logprobs": None, "finish_reason": "stop"}
            ],
        }

        yield f"data: {json.dumps(finish_message)}\n\n"
        yield f"data: [DONE]"

    return StreamingResponse(stream_content(), media_type="text/event-stream")


@app.get("/")
async def get_status():
    return {"status": True}
