from typing import Literal

from fastapi import BackgroundTasks
from fastapi import FastAPI
from fastapi import (
    HTTPException,
    status,
    Depends,
)
from fastapi.middleware.cors import CORSMiddleware
from openai.types.beta.vector_store_deleted import VectorStoreDeleted
from openai.types.beta.vector_stores import VectorStoreFileDeleted
from openai.types.beta.vector_stores.vector_store_file import LastError as LastErrorModel

from apps.openai.models.files import FileContents, Files
from apps.openai.models.vector_stores import VectorStoreFiles
from apps.openai.models.vector_stores import VectorStores, CreateVectorStoreForm, \
    ModifyVectorStoreForm, CreateVectorStoreFileForm
from utils.pipelines.auth import get_current_user

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/")
async def create_vector_store(background_tasks: BackgroundTasks,
                              form_data: CreateVectorStoreForm,
                              user: str = Depends(get_current_user)):
    try:
        vector_store = VectorStores.create_vector_store(form_data)
        if form_data.file_ids:
            for file_id in form_data.file_ids:
                vector_store_file_form = CreateVectorStoreFileForm(file_id=file_id,
                                                                   chunking_strategy=form_data.chunking_strategy)
                await insert_vector_store_file(background_tasks, vector_store_file_form, vector_store.id)
        return VectorStores.get_vector_store(vector_store.id)
    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{str(e)}"
        )


@app.delete("/{vector_store_id}")
async def delete_vector_store(vector_store_id: str,
                              user: str = Depends(get_current_user)):
    try:
        VectorStores.delete_vector_store_by_id(vector_store_id)
        return VectorStoreDeleted(
            id=vector_store_id,
            deleted=True,
            object="vector_store.deleted",
        )
    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{str(e)}",
        )


@app.get("/")
async def list_vector_stores(limit: int | None = None,
                             order: str | None = None,
                             after: str | None = None,
                             before: str | None = None,
                             user: str = Depends(get_current_user)):
    try:
        vector_stores, has_more = VectorStores.list_vector_stores(limit, order, after, before)
        first_id = vector_stores[0].id if len(vector_stores) > 0 else None
        last_id = vector_stores[-1].id if len(vector_stores) > 0 else None
        return {
            "object": "list",
            "data": vector_stores,
            "first_id": first_id,
            "last_id": last_id,
            "has_more": has_more
        }
    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{str(e)}",
        )


@app.get("/{vector_store_id}")
async def retrieve_vector_store(vector_store_id: str,
                                user: str = Depends(get_current_user)):
    try:
        return VectorStores.get_vector_store(vector_store_id)
    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{str(e)}",
        )


@app.post("/{vector_store_id}")
async def modify_vector_store(vector_store_id: str,
                              form_data: ModifyVectorStoreForm,
                              user: str = Depends(get_current_user)):
    try:
        return VectorStores.modify_vector_store(vector_store_id, form_data)
    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{str(e)}",
        )


@app.post("/{vector_store_id}/files")
async def create_vector_store_file(background_tasks: BackgroundTasks,
                                   vector_store_id: str,
                                   form_data: CreateVectorStoreFileForm,
                                   user: str = Depends(get_current_user)):
    try:
        return await insert_vector_store_file(background_tasks, form_data, vector_store_id)
    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{str(e)}",
        )


async def insert_vector_store_file(background_tasks, form_data, vector_store_id):
    vector_store_file = VectorStoreFiles.create_vector_store_file(vector_store_id, form_data)
    VectorStores.refresh_files_count(vector_store_id)
    vector_store = VectorStores.get_vector_store(vector_store_id)
    pipeline_id = vector_store.metadata.get("pipeline_id", None)
    if pipeline_id:
        file = Files.get_file(form_data.file_id)
        content = FileContents.get_file_content(form_data.file_id)
        background_tasks.add_task(add_vector_store_file,
                                  pipeline_id,
                                  vector_store_file.id,
                                  file.filename,
                                  content,
                                  vector_store_id)
    return vector_store_file


@app.get("/{vector_store_id}/files/{file_id}")
async def get_vector_store_file(vector_store_id: str,
                                file_id: str,
                                user: str = Depends(get_current_user)):
    try:
        return VectorStoreFiles.get_vector_store_file(vector_store_id, file_id)
    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{str(e)}",
        )


@app.delete("/{vector_store_id}/files/{file_id}")
async def delete_vector_store_file(background_tasks: BackgroundTasks,
                                   vector_store_id: str,
                                   file_id: str,
                                   user: str = Depends(get_current_user)):
    try:
        vector_store_file = VectorStoreFiles.get_vector_store_file(vector_store_id, file_id)
        vector_store_file_status: str = vector_store_file.status
        VectorStoreFiles.delete_vector_store_file(vector_store_file.id)

        vector_store = VectorStores.get_vector_store(vector_store_id)
        pipeline_id = vector_store.metadata.get("pipeline_id", None)
        if pipeline_id:
            background_tasks.add_task(remove_vector_store_file,
                                      vector_store_file_status,
                                      pipeline_id,
                                      vector_store_file.id,
                                      vector_store.id)

        return VectorStoreFileDeleted(
            id=file_id,
            deleted=True,
            object="vector_store.file.deleted"
        )

    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{str(e)}",
        )


@app.get("/{vector_store_id}/files")
async def list_vector_store_files(limit: int | None = None,
                                  order: str | None = None,
                                  after: str | None = None,
                                  before: str | None = None,
                                  filter: Literal["in_progress", "completed", "failed", "cancelled"] | None = None,
                                  user: str = Depends(get_current_user)):
    try:
        vector_store_files, has_more = VectorStoreFiles.list_vector_store_files(limit, order, after, before, filter)
        first_id = vector_store_files[0].id if len(vector_store_files) > 0 else None
        last_id = vector_store_files[-1].id if len(vector_store_files) > 0 else None
        return {
            "object": "list",
            "data": vector_store_files,
            "first_id": first_id,
            "last_id": last_id,
            "has_more": has_more
        }
    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{str(e)}",
        )


async def add_vector_store_file(pipeline_id: str,
                                vector_store_file_id: str,
                                filename: str,
                                content: bytes,
                                vector_store_id: str):
    if pipeline_id not in app.state.PIPELINES:
        return

    try:
        pipeline = app.state.PIPELINES[pipeline_id]
        if pipeline["type"] == "manifold":
            pipeline_id = pipeline_id.split(".")[0]
    except:
        pass

    pipeline = app.state.PIPELINE_MODULES[pipeline_id]

    try:
        if hasattr(pipeline, "add_vector_store_file"):
            usage_bytes_total, used_bytes_file = pipeline.add_vector_store_file(vector_store_file_id, filename, content)
            VectorStoreFiles.update_status(vector_store_file_id, "completed")
            VectorStoreFiles.update_usage_bytes(vector_store_file_id, used_bytes_file)
            VectorStores.update_usage_bytes(vector_store_id, usage_bytes_total)
            VectorStores.refresh_files_count(vector_store_id)
    except Exception as e:
        print(e)
        VectorStoreFiles.update_status(vector_store_file_id,
                                       "failed",
                                       LastErrorModel(code="internal_error", message=str(e)))
        VectorStores.refresh_files_count(vector_store_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{str(e)}",
        )


async def remove_vector_store_file(status: str,
                                   pipeline_id: str,
                                   vector_store_file_id: str,
                                   vector_store_id: str):
    if pipeline_id not in app.state.PIPELINES:
        return

    try:
        pipeline = app.state.PIPELINES[pipeline_id]
        if pipeline["type"] == "manifold":
            pipeline_id = pipeline_id.split(".")[0]
    except:
        pass

    pipeline = app.state.PIPELINE_MODULES[pipeline_id]

    try:
        if hasattr(pipeline, "remove_vector_store_file"):
            usage_bytes = pipeline.remove_vector_store_file(vector_store_file_id)
            VectorStores.update_usage_bytes(vector_store_id, usage_bytes)
            VectorStores.refresh_files_count(vector_store_id)
    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{str(e)}",
        )
