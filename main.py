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
from schemas import FilterForm, OpenAIChatCompletionForm

import os
import importlib.util

import logging

from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor


import os

####################################
# Load .env file
####################################

try:
    from dotenv import load_dotenv, find_dotenv

    load_dotenv(find_dotenv(".env"))
except ImportError:
    print("dotenv not installed, skipping...")


PIPELINES = {}
PIPELINE_MODULES = {}


def on_startup():
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
        logging.info("Loaded:", loaded_module.__name__)

        pipeline = loaded_module.Pipeline()
        pipeline_id = pipeline.id if hasattr(pipeline, "id") else loaded_module.__name__

        PIPELINE_MODULES[pipeline_id] = pipeline

        if hasattr(pipeline, "type"):
            if pipeline.type == "manifold":
                for p in pipeline.pipelines:
                    manifold_pipeline_id = f'{pipeline_id}.{p["id"]}'

                    manifold_pipeline_name = p["name"]
                    if hasattr(pipeline, "name"):
                        manifold_pipeline_name = (
                            f"{pipeline.name}{manifold_pipeline_name}"
                        )

                    PIPELINES[manifold_pipeline_id] = {
                        "module": pipeline_id,
                        "type": pipeline.type if hasattr(pipeline, "type") else "pipe",
                        "id": manifold_pipeline_id,
                        "name": manifold_pipeline_name,
                        "valves": (
                            pipeline.valves if hasattr(pipeline, "valves") else None
                        ),
                    }
            if pipeline.type == "filter":
                PIPELINES[pipeline_id] = {
                    "module": pipeline_id,
                    "type": (pipeline.type if hasattr(pipeline, "type") else "pipe"),
                    "id": pipeline_id,
                    "name": (
                        pipeline.name if hasattr(pipeline, "name") else pipeline_id
                    ),
                    "pipelines": (
                        pipeline.valves.pipelines
                        if hasattr(pipeline, "valves")
                        and hasattr(pipeline.valves, "pipelines")
                        else []
                    ),
                    "priority": (
                        pipeline.valves.priority
                        if hasattr(pipeline, "valves")
                        and hasattr(pipeline.valves, "priority")
                        else 0
                    ),
                    "valves": pipeline.valves if hasattr(pipeline, "valves") else None,
                }
        else:
            PIPELINES[pipeline_id] = {
                "module": pipeline_id,
                "type": (pipeline.type if hasattr(pipeline, "type") else "pipe"),
                "id": pipeline_id,
                "name": (pipeline.name if hasattr(pipeline, "name") else pipeline_id),
                "valves": pipeline.valves if hasattr(pipeline, "valves") else None,
            }


on_startup()


@asynccontextmanager
async def lifespan(app: FastAPI):
    for module in PIPELINE_MODULES.values():
        if hasattr(module, "on_startup"):
            await module.on_startup()
    yield

    for module in PIPELINE_MODULES.values():
        if hasattr(module, "on_shutdown"):
            await module.on_shutdown()


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
                "pipeline": {
                    "type": pipeline["type"],
                    **(
                        {
                            "pipelines": pipeline.get("pipelines", []),
                            "priority": pipeline.get("priority", 0),
                        }
                        if pipeline.get("type", "pipe") == "filter"
                        else {}
                    ),
                    "valves": pipeline["valves"] != None,
                },
            }
            for pipeline in app.state.PIPELINES.values()
        ]
    }


@app.get("/{pipeline_id}/valves")
async def get_valves(pipeline_id: str):
    if pipeline_id not in app.state.PIPELINES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline {pipeline_id} not found",
        )

    pipeline = app.state.PIPELINES[pipeline_id]
    if not pipeline.get("valves", False):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Valves for {pipeline_id} not found",
        )
    if pipeline["type"] == "manifold":
        manifold_id, pipeline_id = pipeline_id.split(".", 1)
        pipeline_id = manifold_id

    pipeline_module = PIPELINE_MODULES[pipeline_id]
    return pipeline_module.valves


@app.get("/{pipeline_id}/valves/spec")
async def get_valves_spec(pipeline_id: str):

    if pipeline_id not in app.state.PIPELINES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline {pipeline_id} not found",
        )

    pipeline = app.state.PIPELINES[pipeline_id]

    if not pipeline.get("valves", False):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Valves for {pipeline_id} not found",
        )
    if pipeline["type"] == "manifold":
        manifold_id, pipeline_id = pipeline_id.split(".", 1)
        pipeline_id = manifold_id

    pipeline_module = PIPELINE_MODULES[pipeline_id]
    return pipeline_module.valves.schema()


@app.post("/{pipeline_id}/valves/update")
async def update_valves(pipeline_id: str, form_data: dict):

    if pipeline_id not in app.state.PIPELINES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline {pipeline_id} not found",
        )

    pipeline = app.state.PIPELINES[pipeline_id]
    if not pipeline.get("valves", False):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Valves for {pipeline_id} not found",
        )
    if pipeline["type"] == "manifold":
        manifold_id, pipeline_id = pipeline_id.split(".", 1)
        pipeline_id = manifold_id

    pipeline_module = PIPELINE_MODULES[pipeline_id]

    await pipeline_module.on_shutdown()
    try:
        ValvesModel = pipeline_module.valves.__class__
        valves = ValvesModel(**form_data)
        pipeline_module.valves = valves
    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{str(e)}",
        )
    await pipeline_module.on_startup()

    return pipeline_module.valves


@app.post("/{pipeline_id}/filter")
async def filter(pipeline_id: str, form_data: FilterForm):
    if (
        pipeline_id not in app.state.PIPELINES
        or app.state.PIPELINES[pipeline_id].get("type", "pipe") != "filter"
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Filter {pipeline_id} not found",
        )

    pipeline = PIPELINE_MODULES[pipeline_id]

    try:
        body = await pipeline.filter(form_data.body, form_data.user)
        return body
    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{str(e)}",
        )


@app.post("/chat/completions")
@app.post("/v1/chat/completions")
async def generate_openai_chat_completion(form_data: OpenAIChatCompletionForm):
    user_message = get_last_user_message(form_data.messages)
    messages = [message.model_dump() for message in form_data.messages]

    if (
        form_data.model not in app.state.PIPELINES
        or app.state.PIPELINES[form_data.model]["type"] == "filter"
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline {form_data.model} not found",
        )

    def job():
        print(form_data.model)

        pipeline = app.state.PIPELINES[form_data.model]
        pipeline_id = form_data.model

        print(pipeline_id)

        if pipeline["type"] == "manifold":
            manifold_id, pipeline_id = pipeline_id.split(".", 1)
            pipe = PIPELINE_MODULES[manifold_id].pipe
        else:
            pipe = PIPELINE_MODULES[pipeline_id].pipe

        if form_data.stream:

            def stream_content():
                res = pipe(
                    user_message=user_message,
                    model_id=pipeline_id,
                    messages=messages,
                    body=form_data.model_dump(),
                )

                logging.info(f"stream:true:{res}")

                if isinstance(res, str):
                    message = stream_message_template(form_data.model, res)
                    logging.info(f"stream_content:str:{message}")
                    yield f"data: {json.dumps(message)}\n\n"

                if isinstance(res, Iterator):
                    for line in res:
                        if isinstance(line, BaseModel):
                            line = line.model_dump_json()
                            line = f"data: {line}"

                        try:
                            line = line.decode("utf-8")
                        except:
                            pass

                        logging.info(f"stream_content:Generator:{line}")

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
            res = pipe(
                user_message=user_message,
                model_id=pipeline_id,
                messages=messages,
                body=form_data.model_dump(),
            )
            logging.info(f"stream:false:{res}")

            if isinstance(res, dict):
                return res
            elif isinstance(res, BaseModel):
                return res.model_dump()
            else:

                message = ""

                if isinstance(res, str):
                    message = res

                if isinstance(res, Generator):
                    for stream in res:
                        message = f"{message}{stream}"

                logging.info(f"stream:false:{message}")
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
