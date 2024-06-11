"""
title: Llama Index Embedding Pipeline
author: open-webui
date: 2024-06-11
version: 1.0
license: MIT
description: A pipeline for retrieving relevant information and generating a knowledge base using the Llama Index library
requirements: llama-index-core, llama-index-vector-stores-qdrant, llama-index-embeddings-openai, qdrant-client
"""
import os
from typing import List, Union, Generator, Iterator

from llama_index.core.ingestion import IngestionPipeline
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index_client import SentenceSplitter
from pydantic import BaseModel
from qdrant_client import QdrantClient, models
from llama_index.core import VectorStoreIndex, Document


class Pipeline:
    class Valves(BaseModel):
        LLM: str
        QDRANT_HTTP_HOST: str
        QDRANT_HTTP_PORT: int
        LLM_BASE_URL: str
        LLM_API_KEY: str
        EMBEDDING_MODEL_BASE_URL: str
        EMBEDDING_MODEL_API_KEY: str
        RAG_EMBEDDING_MODEL: str
        SIMILARITY_TOP_K: int
        RAG_TEMPLATE: str
        TEMPERATURE: float
        CHUNK_SIZE: int
        CHUNK_OVERLAP: int

    def __init__(self):
        self.collection_name = "Documents"
        self.qdrant_client = None
        self.index = None
        self.vector_store = None
        self.name = "llamaindex_qdrant_embedding_pipeline"
        self.valves = self.Valves(
            **{
                "LLM": os.getenv("LLM"),
                "QDRANT_HTTP_HOST": os.getenv("QDRANT_HTTP_HOST"),
                "QDRANT_HTTP_PORT": os.getenv("QDRANT_HTTP_PORT"),
                "LLM_BASE_URL": os.getenv("LLM_BASE_URL"),
                "LLM_API_KEY": os.getenv("LLM_API_KEY"),
                "EMBEDDING_MODEL_BASE_URL": os.getenv("EMBEDDING_MODEL_BASE_URL"),
                "EMBEDDING_MODEL_API_KEY": os.getenv("EMBEDDING_MODEL_API_KEY"),
                "RAG_EMBEDDING_MODEL": os.getenv("RAG_EMBEDDING_MODEL"),
                "SIMILARITY_TOP_K": os.getenv("SIMILARITY_TOP_K"),
                "RAG_TEMPLATE": os.getenv("RAG_TEMPLATE"),
                "TEMPERATURE": float(os.getenv("TEMPERATURE")),
                "CHUNK_SIZE": os.getenv("CHUNK_SIZE"),
                "CHUNK_OVERLAP": os.getenv("CHUNK_OVERLAP"),
            }
        )

    async def on_startup(self):
        self.qdrant_client = QdrantClient(
            host=self.valves.QDRANT_HTTP_HOST,
            port=self.valves.QDRANT_HTTP_PORT,
        )
        self.vector_store = QdrantVectorStore(client=self.qdrant_client,
                                              collection_name=self.collection_name,
                                              batch_size=5)
        embed_model = OpenAIEmbedding(model_name=self.valves.RAG_EMBEDDING_MODEL,
                                      api_base=self.valves.EMBEDDING_MODEL_BASE_URL,
                                      api_key=self.valves.EMBEDDING_MODEL_API_KEY)
        self.index: VectorStoreIndex = VectorStoreIndex.from_vector_store(self.vector_store, embed_model=embed_model)
        # This function is called when the server is started.
        pass

    async def on_shutdown(self):
        # This function is called when the server is stopped.
        pass

    def pipe(
            self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        # This is where you can add your custom RAG pipeline.
        # Typically, you would retrieve relevant information from your knowledge base and synthesize it to generate a response.

        print(messages)
        print(user_message)

        query_engine = self.index.as_query_engine(streaming=True)
        response = query_engine.query(user_message)

        return response.response_gen

    def embed(self, body: dict):
        # This is where you can store your document chunks in a vector database
        text = body["text"]
        metadata = body["metadata"]
        doc = Document(text=text, metadata=metadata)
        ingestion_pipeline = IngestionPipeline(
            transformations=[
                SentenceSplitter(chunk_size=self.valves.CHUNK_SIZE, chunk_overlap=self.valves.CHUNK_OVERLAP),
                OpenAIEmbedding(model_name=self.valves.RAG_EMBEDDING_MODEL,
                                api_base=self.valves.EMBEDDING_MODEL_BASE_URL,
                                api_key=self.valves.EMBEDDING_MODEL_API_KEY),
            ],
            vector_store=self.vector_store
        )
        ingestion_pipeline.run(documents=[doc])

    def delete_nodes(self, body: dict, metadata_key: str | None, metadata_value: dict | None):
        # This is where you can delete your document chunks from the vector database
        if metadata_key is None or metadata_value is None:
            for col in self.qdrant_client.get_collections().collections:
                self.qdrant_client.delete_collection(collection_name=col.name)
        else:
            self.qdrant_client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(key=metadata_key, match=models.MatchValue(value=metadata_value)),
                        ],
                    )
                ),
            )
