from fastapi import FastAPI, Request, Depends, status, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool


from starlette.responses import StreamingResponse, Response
from pydantic import BaseModel, ConfigDict
from typing import List, Union, Generator, Iterator


import time
import json
import uuid

from utils import get_last_user_message, stream_message_template
from schemas import OpenAIChatCompletionForm

import os
import importlib.util


from concurrent.futures import ThreadPoolExecutor

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

    pipeline = loaded_module.Pipeline()

    PIPELINES[loaded_module.__name__] = {
        "module": pipeline,
        "id": loaded_module.__name__,
        "name": loaded_module.__name__,
    }


from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    for pipeline in PIPELINES.values():
        if hasattr(pipeline["module"], "on_startup"):
            await pipeline["module"].on_startup()
    yield

    for pipeline in PIPELINES.values():

        if hasattr(pipeline["module"], "on_shutdown"):
            await pipeline["module"].on_shutdown()


app = FastAPI(docs_url="/docs", redoc_url=None, lifespan=lifespan)

app.state.PIPELINES = PIPELINES


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
async def generate_openai_chat_completion(form_data: OpenAIChatCompletionForm):
    user_message = get_last_user_message(form_data.messages)

    if form_data.model not in app.state.PIPELINES:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {form_data.model} not found",
        )

    def job():
        print(form_data.model)
        get_response = app.state.PIPELINES[form_data.model]["module"].get_response

        if form_data.stream:

            def stream_content():
                res = get_response(
                    user_message,
                    messages=form_data.messages,
                    body=form_data.model_dump(),
                )

                print(f"stream:true:{res}")

                if isinstance(res, str):
                    message = stream_message_template(form_data.model, res)
                    print(f"stream_content:str:{message}")
                    yield f"data: {json.dumps(message)}\n\n"

                if isinstance(res, Iterator):
                    for line in res:
                        try:
                            line = line.decode("utf-8")
                        except:
                            pass

                        print(f"stream_content:Generator:{line}")

                        if line.startswith("data:"):
                            yield f"{line}\n\n"
                        else:
                            line = stream_message_template(form_data.model, line)
                            yield f"data: {json.dumps(line)}\n\n"

                if isinstance(res, str) or isinstance(res, Generator):
                    finish_message = {
                        "id": f"{form_data.model}-{str(uuid.uuid4())}",
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": form_data.model,
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
            res = get_response(
                user_message,
                messages=form_data.messages,
                body=form_data.model_dump(),
            )
            print(f"stream:false:{res}")

            if isinstance(res, dict):
                return res
            else:
                message = ""

                if isinstance(res, str):
                    message = res

                elif isinstance(res, Generator):
                    for stream in res:
                        message = f"{message}{stream}"

                print(f"stream:false:{message}")

                return {
                    "id": f"{form_data.model}-{str(uuid.uuid4())}",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": form_data.model,
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

    return await run_in_threadpool(job)


@app.get("/")
async def get_status():
    return {"status": True}
