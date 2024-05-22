from fastapi import FastAPI, Request, Depends, status, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool


from starlette.responses import StreamingResponse, Response
from pydantic import BaseModel, ConfigDict
from typing import List, Union, Generator


import time
import json
import uuid

from utils import get_last_user_message, stream_message_template
from schemas import OpenAIChatCompletionForm
from config import MODEL_ID, MODEL_NAME

import os
import importlib.util


PIPELINES = {}


def load_modules_from_directory(directory):
    for filename in os.listdir(directory):
        if filename.endswith(".py"):
            module_name = filename[:-3]  # Remove the .py extension
            module_path = os.path.join(directory, filename)
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            yield module


for loaded_module in load_modules_from_directory("./pipelines"):
    # Do something with the loaded module
    print("Loaded:", loaded_module.__name__)
    PIPELINES[loaded_module.__name__] = {
        "module": loaded_module,
        "id": loaded_module.__name__,
        "name": loaded_module.__name__,
    }


from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    for pipeline in PIPELINES.values():
        if hasattr(pipeline["module"], "on_startup"):
            info = await pipeline["module"].on_startup()
            if info:
                pipeline["id"] = info["id"]
                pipeline["name"] = info["name"]
    yield

    for pipeline in PIPELINES.values():
        if hasattr(pipeline["module"], "on_shutdown"):
            await pipeline["module"].on_shutdown()


app = FastAPI(docs_url="/docs", redoc_url=None, lifespan=lifespan)


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
    Returns the available pipelines
    """
    return {
        "data": [
            {
                "id": pipeline["id"],
                "name": pipeline["name"],
                "object": "model",
                "created": int(time.time()),
                "owned_by": "openai",
            }
            for pipeline in PIPELINES.values()
        ]
    }


@app.post("/chat/completions")
@app.post("/v1/chat/completions")
def generate_openai_chat_completion(form_data: OpenAIChatCompletionForm):
    user_message = get_last_user_message(form_data.messages)

    if form_data.model not in PIPELINES:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {form_data.model} not found",
        )

    def job():
        get_response = PIPELINES[form_data.model]["module"].get_response

        if form_data.stream:

            def stream_content():
                res = get_response(user_message, messages=form_data.messages)

                if isinstance(res, str):
                    message = stream_message_template(res)
                    yield f"data: {json.dumps(message)}\n\n"

                elif isinstance(res, Generator):
                    for message in res:
                        print(message)
                        message = stream_message_template(message)
                        yield f"data: {json.dumps(message)}\n\n"

                finish_message = {
                    "id": f"{form_data.model}-{str(uuid.uuid4())}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": MODEL_ID,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "logprobs": None,
                            "finish_reason": "stop",
                        }
                    ],
                }

                yield f"data: {json.dumps(finish_message)}\n\n"
                yield f"data: [DONE]"

            return StreamingResponse(stream_content(), media_type="text/event-stream")
        else:
            res = get_response(user_message, messages=form_data.messages)
            message = ""

            if isinstance(res, str):
                message = res

            elif isinstance(res, Generator):
                for stream in res:
                    message = f"{message}{stream}"

            return {
                "id": f"{form_data.model}-{str(uuid.uuid4())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": MODEL_ID,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": message,
                        },
                        "logprobs": None,
                        "finish_reason": "stop",
                    }
                ],
            }

    return job()


@app.get("/")
async def get_status():
    return {"status": True}
