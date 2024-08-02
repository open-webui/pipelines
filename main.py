from fastapi import FastAPI, Request, Depends, status, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool


from starlette.responses import StreamingResponse, Response
from pydantic import BaseModel, ConfigDict
from typing import List, Union, Generator, Iterator


from utils.pipelines.auth import bearer_security, get_current_user
from utils.pipelines.main import get_last_user_message, stream_message_template
from utils.pipelines.misc import convert_to_raw_url

from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from schemas import FilterForm, OpenAIChatCompletionForm
from urllib.parse import urlparse

import shutil
import aiohttp
import os
import importlib.util
import logging
import time
import json
import uuid
import sys
import subprocess


from config import API_KEY, PIPELINES_DIR

if not os.path.exists(PIPELINES_DIR):
    os.makedirs(PIPELINES_DIR)


PIPELINES = {}
PIPELINE_MODULES = {}
PIPELINE_NAMES = {}


def get_all_pipelines():
    pipelines = {}
    for pipeline_id in PIPELINE_MODULES.keys():
        pipeline = PIPELINE_MODULES[pipeline_id]

        if hasattr(pipeline, "type"):
            if pipeline.type == "manifold":
                manifold_pipelines = []

                # Check if pipelines is a function or a list
                if callable(pipeline.pipelines):
                    manifold_pipelines = pipeline.pipelines()
                else:
                    manifold_pipelines = pipeline.pipelines

                for p in manifold_pipelines:
                    manifold_pipeline_id = f'{pipeline_id}.{p["id"]}'

                    manifold_pipeline_name = p["name"]
                    if hasattr(pipeline, "name"):
                        manifold_pipeline_name = (
                            f"{pipeline.name}{manifold_pipeline_name}"
                        )

                    pipelines[manifold_pipeline_id] = {
                        "module": pipeline_id,
                        "type": pipeline.type if hasattr(pipeline, "type") else "pipe",
                        "id": manifold_pipeline_id,
                        "name": manifold_pipeline_name,
                        "valves": (
                            pipeline.valves if hasattr(pipeline, "valves") else None
                        ),
                    }
            if pipeline.type == "filter":
                pipelines[pipeline_id] = {
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
            pipelines[pipeline_id] = {
                "module": pipeline_id,
                "type": (pipeline.type if hasattr(pipeline, "type") else "pipe"),
                "id": pipeline_id,
                "name": (pipeline.name if hasattr(pipeline, "name") else pipeline_id),
                "valves": pipeline.valves if hasattr(pipeline, "valves") else None,
            }

    return pipelines

def parse_frontmatter(content):
    frontmatter = {}
    for line in content.split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            frontmatter[key.strip().lower()] = value.strip()
    return frontmatter

def install_frontmatter_requirements(requirements):
    if requirements:
        req_list = [req.strip() for req in requirements.split(',')]
        for req in req_list:
            print(f"Installing requirement: {req}")
            subprocess.check_call([sys.executable, "-m", "pip", "install", req])
    else:
        print("No requirements found in frontmatter.")

async def load_module_from_path(module_name, module_path):

    try:
        # Read the module content
        with open(module_path, 'r') as file:
            content = file.read()

        # Parse frontmatter
        frontmatter = {}
        if content.startswith('"""'):
            end = content.find('"""', 3)
            if end != -1:
                frontmatter_content = content[3:end]
                frontmatter = parse_frontmatter(frontmatter_content)

        # Install requirements if specified
        if 'requirements' in frontmatter:
            install_frontmatter_requirements(frontmatter['requirements'])

        # Load the module
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        print(f"Loaded module: {module.__name__}")
        if hasattr(module, "Pipeline"):
            return module.Pipeline()
        else:
            raise Exception("No Pipeline class found")
    except Exception as e:
        print(f"Error loading module: {module_name}")

        # Move the file to the error folder
        failed_pipelines_folder = os.path.join(PIPELINES_DIR, "failed")
        if not os.path.exists(failed_pipelines_folder):
            os.makedirs(failed_pipelines_folder)

        failed_file_path = os.path.join(failed_pipelines_folder, f"{module_name}.py")
        os.rename(module_path, failed_file_path)
        print(e)
    return None


async def load_modules_from_directory(directory):
    global PIPELINE_MODULES
    global PIPELINE_NAMES

    for filename in os.listdir(directory):
        if filename.endswith(".py"):
            module_name = filename[:-3]  # Remove the .py extension
            module_path = os.path.join(directory, filename)

            # Create subfolder matching the filename without the .py extension
            subfolder_path = os.path.join(directory, module_name)
            if not os.path.exists(subfolder_path):
                os.makedirs(subfolder_path)
                logging.info(f"Created subfolder: {subfolder_path}")

            # Create a valves.json file if it doesn't exist
            valves_json_path = os.path.join(subfolder_path, "valves.json")
            if not os.path.exists(valves_json_path):
                with open(valves_json_path, "w") as f:
                    json.dump({}, f)
                logging.info(f"Created valves.json in: {subfolder_path}")

            pipeline = await load_module_from_path(module_name, module_path)
            if pipeline:
                # Overwrite pipeline.valves with values from valves.json
                if os.path.exists(valves_json_path):
                    with open(valves_json_path, "r") as f:
                        valves_json = json.load(f)
                        if hasattr(pipeline, "valves"):
                            ValvesModel = pipeline.valves.__class__
                            # Create a ValvesModel instance using default values and overwrite with valves_json
                            combined_valves = {
                                **pipeline.valves.model_dump(),
                                **valves_json,
                            }
                            valves = ValvesModel(**combined_valves)
                            pipeline.valves = valves

                            logging.info(f"Updated valves for module: {module_name}")

                pipeline_id = pipeline.id if hasattr(pipeline, "id") else module_name
                PIPELINE_MODULES[pipeline_id] = pipeline
                PIPELINE_NAMES[pipeline_id] = module_name
                logging.info(f"Loaded module: {module_name}")
            else:
                logging.warning(f"No Pipeline class found in {module_name}")

    global PIPELINES
    PIPELINES = get_all_pipelines()


async def on_startup():
    await load_modules_from_directory(PIPELINES_DIR)

    for module in PIPELINE_MODULES.values():
        if hasattr(module, "on_startup"):
            await module.on_startup()


async def on_shutdown():
    for module in PIPELINE_MODULES.values():
        if hasattr(module, "on_shutdown"):
            await module.on_shutdown()


async def reload():
    await on_shutdown()
    # Clear existing pipelines
    PIPELINES.clear()
    PIPELINE_MODULES.clear()
    PIPELINE_NAMES.clear()
    # Load pipelines afresh
    await on_startup()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await on_startup()
    yield
    await on_shutdown()


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
    app.state.PIPELINES = get_all_pipelines()
    response = await call_next(request)
    process_time = int(time.time()) - start_time
    response.headers["X-Process-Time"] = str(process_time)

    return response


@app.get("/v1/models")
@app.get("/models")
async def get_models():
    """
    Returns the available pipelines
    """
    app.state.PIPELINES = get_all_pipelines()
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
                            "pipelines": (
                                pipeline["valves"].pipelines
                                if pipeline.get("valves", None)
                                else []
                            ),
                            "priority": pipeline.get("priority", 0),
                        }
                        if pipeline.get("type", "pipe") == "filter"
                        else {}
                    ),
                    "valves": pipeline["valves"] != None,
                },
            }
            for pipeline in app.state.PIPELINES.values()
        ],
        "object": "list",
        "pipelines": True,
    }


@app.get("/v1")
@app.get("/")
async def get_status():
    return {"status": True}


@app.get("/v1/pipelines")
@app.get("/pipelines")
async def list_pipelines(user: str = Depends(get_current_user)):
    if user == API_KEY:
        return {
            "data": [
                {
                    "id": pipeline_id,
                    "name": PIPELINE_NAMES[pipeline_id],
                    "type": (
                        PIPELINE_MODULES[pipeline_id].type
                        if hasattr(PIPELINE_MODULES[pipeline_id], "type")
                        else "pipe"
                    ),
                    "valves": (
                        True
                        if hasattr(PIPELINE_MODULES[pipeline_id], "valves")
                        else False
                    ),
                }
                for pipeline_id in list(PIPELINE_MODULES.keys())
            ]
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


class AddPipelineForm(BaseModel):
    url: str


async def download_file(url: str, dest_folder: str):
    filename = os.path.basename(urlparse(url).path)
    if not filename.endswith(".py"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL must point to a Python file",
        )

    file_path = os.path.join(dest_folder, filename)

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to download file",
                )
            with open(file_path, "wb") as f:
                f.write(await response.read())

    return file_path


@app.post("/v1/pipelines/add")
@app.post("/pipelines/add")
async def add_pipeline(
    form_data: AddPipelineForm, user: str = Depends(get_current_user)
):
    if user != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    try:
        url = convert_to_raw_url(form_data.url)

        print(url)
        file_path = await download_file(url, dest_folder=PIPELINES_DIR)
        await reload()
        return {
            "status": True,
            "detail": f"Pipeline added successfully from {file_path}",
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@app.post("/v1/pipelines/upload")
@app.post("/pipelines/upload")
async def upload_pipeline(
    file: UploadFile = File(...), user: str = Depends(get_current_user)
):
    if user != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    file_ext = os.path.splitext(file.filename)[1]
    if file_ext != ".py":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only Python files are allowed.",
        )

    try:
        # Ensure the destination folder exists
        os.makedirs(PIPELINES_DIR, exist_ok=True)

        # Define the file path
        file_path = os.path.join(PIPELINES_DIR, file.filename)

        # Save the uploaded file to the specified directory
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Perform any necessary reload or processing
        await reload()

        return {
            "status": True,
            "detail": f"Pipeline uploaded successfully to {file_path}",
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


class DeletePipelineForm(BaseModel):
    id: str


@app.delete("/v1/pipelines/delete")
@app.delete("/pipelines/delete")
async def delete_pipeline(
    form_data: DeletePipelineForm, user: str = Depends(get_current_user)
):
    if user != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    pipeline_id = form_data.id
    pipeline_name = PIPELINE_NAMES.get(pipeline_id.split(".")[0], None)

    if PIPELINE_MODULES[pipeline_id]:
        if hasattr(PIPELINE_MODULES[pipeline_id], "on_shutdown"):
            await PIPELINE_MODULES[pipeline_id].on_shutdown()

    pipeline_path = os.path.join(PIPELINES_DIR, f"{pipeline_name}.py")
    if os.path.exists(pipeline_path):
        os.remove(pipeline_path)
        await reload()
        return {
            "status": True,
            "detail": f"Pipeline {pipeline_id} deleted successfully",
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline {pipeline_id} not found",
        )


@app.post("/v1/pipelines/reload")
@app.post("/pipelines/reload")
async def reload_pipelines(user: str = Depends(get_current_user)):
    if user == API_KEY:
        await reload()
        return {"message": "Pipelines reloaded successfully."}
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


@app.get("/v1/{pipeline_id}/valves")
@app.get("/{pipeline_id}/valves")
async def get_valves(pipeline_id: str):
    if pipeline_id not in PIPELINE_MODULES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline {pipeline_id} not found",
        )

    pipeline = PIPELINE_MODULES[pipeline_id]

    if hasattr(pipeline, "valves") is False:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Valves for {pipeline_id} not found",
        )

    return pipeline.valves


@app.get("/v1/{pipeline_id}/valves/spec")
@app.get("/{pipeline_id}/valves/spec")
async def get_valves_spec(pipeline_id: str):
    if pipeline_id not in PIPELINE_MODULES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline {pipeline_id} not found",
        )

    pipeline = PIPELINE_MODULES[pipeline_id]

    if hasattr(pipeline, "valves") is False:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Valves for {pipeline_id} not found",
        )

    return pipeline.valves.schema()


@app.post("/v1/{pipeline_id}/valves/update")
@app.post("/{pipeline_id}/valves/update")
async def update_valves(pipeline_id: str, form_data: dict):

    if pipeline_id not in PIPELINE_MODULES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline {pipeline_id} not found",
        )

    pipeline = PIPELINE_MODULES[pipeline_id]

    if hasattr(pipeline, "valves") is False:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Valves for {pipeline_id} not found",
        )

    try:
        ValvesModel = pipeline.valves.__class__
        valves = ValvesModel(**form_data)
        pipeline.valves = valves

        # Determine the directory path for the valves.json file
        subfolder_path = os.path.join(PIPELINES_DIR, PIPELINE_NAMES[pipeline_id])
        valves_json_path = os.path.join(subfolder_path, "valves.json")

        # Save the updated valves data back to the valves.json file
        with open(valves_json_path, "w") as f:
            json.dump(valves.model_dump(), f)

        if hasattr(pipeline, "on_valves_updated"):
            await pipeline.on_valves_updated()
    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{str(e)}",
        )

    return pipeline.valves


@app.post("/v1/{pipeline_id}/filter/inlet")
@app.post("/{pipeline_id}/filter/inlet")
async def filter_inlet(pipeline_id: str, form_data: FilterForm):
    if pipeline_id not in app.state.PIPELINES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Filter {pipeline_id} not found",
        )

    try:
        pipeline = app.state.PIPELINES[form_data.body["model"]]
        if pipeline["type"] == "manifold":
            pipeline_id = pipeline_id.split(".")[0]
    except:
        pass

    pipeline = PIPELINE_MODULES[pipeline_id]

    try:
        if hasattr(pipeline, "inlet"):
            body = await pipeline.inlet(form_data.body, form_data.user)
            return body
        else:
            return form_data.body
    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{str(e)}",
        )


@app.post("/v1/{pipeline_id}/filter/outlet")
@app.post("/{pipeline_id}/filter/outlet")
async def filter_outlet(pipeline_id: str, form_data: FilterForm):
    if pipeline_id not in app.state.PIPELINES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Filter {pipeline_id} not found",
        )

    try:
        pipeline = app.state.PIPELINES[form_data.body["model"]]
        if pipeline["type"] == "manifold":
            pipeline_id = pipeline_id.split(".")[0]
    except:
        pass

    pipeline = PIPELINE_MODULES[pipeline_id]

    try:
        if hasattr(pipeline, "outlet"):
            body = await pipeline.outlet(form_data.body, form_data.user)
            return body
        else:
            return form_data.body
    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{str(e)}",
        )


@app.post("/v1/chat/completions")
@app.post("/chat/completions")
async def generate_openai_chat_completion(form_data: OpenAIChatCompletionForm):
    messages = [message.model_dump() for message in form_data.messages]
    user_message = get_last_user_message(messages)

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
