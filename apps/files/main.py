import time
from typing import Annotated
from uuid import uuid4

from fastapi import FastAPI, File, Form, UploadFile
from fastapi import (
    HTTPException,
    status,
    Depends,
)
from fastapi.middleware.cors import CORSMiddleware
from openai.types import FileDeleted

from apps.openai.models.files import Files, FileModel, FileContents
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
async def upload_file(purpose: Annotated[str, Form()],
                      file: Annotated[UploadFile, File()],
                      user: str = Depends(get_current_user)):
    try:
        file_bytes: bytes = file.file.read()
        filename: str = file.filename
        created_file = Files.create_file(purpose, filename, file_bytes)
        FileContents.create_file_content(file_id=created_file.id, content=file_bytes)

        return created_file
    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{str(e)}",
        )


@app.delete("/{file_id}")
async def delete_file(file_id: str,
                      user: str = Depends(get_current_user)):
    try:
        deleted = Files.delete_file(file_id)
        return FileDeleted(
            id=file_id,
            object="file",
            deleted=deleted
        )
    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{str(e)}",
        )


@app.get("/{file_id}/content")
async def get_file_content(file_id: str,
                           user: str = Depends(get_current_user)):
    try:
        return FileContents.get_file_content(file_id)
    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{str(e)}",
        )


@app.get("/{file_id}")
async def retrieve_file(file_id: str,
                        user: str = Depends(get_current_user)):
    try:
        return Files.get_file(file_id)
    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{str(e)}",
        )


@app.get("/")
async def list_files(
        purpose: str | None = None,
        user: str = Depends(get_current_user)
):
    try:
        files = Files.get_files(purpose)
        return {"data": files}

    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{str(e)}",
        )
