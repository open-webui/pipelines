"""
title: Vector Store Pipeline
author: open-webui
date: 2024-05-30
version: 1.0
license: MIT
description: A pipeline for creating a knowledge base using the openai files and vector store api
requirements: qdrant-client, llama-index-vector-stores-qdrant
"""


import logging
import os
from typing import List, Union, Generator, Iterator

import qdrant_client
from llama_index.core import VectorStoreIndex, Document
from llama_index.vector_stores.qdrant import QdrantVectorStore
from openai import Client

log = logging.getLogger(__name__)


class Pipeline:

    def __init__(self):
        self.openai_client = None
        self.qdrant_client = None
        self.vector_store = None
        self.index = None
        self.name = "Pipeline"
        self.LLM_BASE_URL = os.getenv("LLM_BASE_URL")
        self.LLM_API_KEY = os.getenv("LLM_API_KEY")
        self.LLM = os.getenv("LLM")
        self.QDRANT_URL = os.getenv("QDRANT_URL")

    async def on_startup(self):
        self.openai_client = Client(api_key=self.LLM_API_KEY,
                                    base_url=self.LLM_BASE_URL,
                                    timeout=None)
        self.qdrant_client = qdrant_client.QdrantClient(url=self.QDRANT_URL)
        self.vector_store = QdrantVectorStore(client=self.qdrant_client, collection_name="Documents")
        self.index = VectorStoreIndex.from_vector_store(self.vector_store, embed_model=None)

    def pipe(
            self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        response = self.openai_client.chat.completions.create(model=self.LLM,
                                                              messages=messages,
                                                              stream=True,
                                                              )
        for chunk in response:
            yield chunk

    def add_vector_store_file(self, vector_store_file_id: str, filename: str, file_content: bytes) -> tuple[int, int]:
        # for sake of simplicity, only .txt files are supported
        if filename.endswith(".txt"):
            text = file_content.decode("utf-8")
            doc = Document(id_=vector_store_file_id, text=text, metadata={"filename": filename})
            self.index.insert(doc)
            # return used vector store storage size in bytes: 
            # first value: total vector store size
            # second value: used vector store storage for this file 
            # for sake of simplicity, 0 is returned
            return 0, 0
        raise ValueError("invalid file type")

    def remove_vector_store_file(self, vector_store_file_id: str) -> int:
        # return total vector store size in bytes
        self.index.delete(doc_id=vector_store_file_id)
        return 0
