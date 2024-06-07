"""
title: Llama Index Pipeline
author: open-webui
date: 2024-06-10
version: 1.0
license: MIT
description: A pipeline for retrieving relevant information from a knowledge base using the Llama Index library.
requirements: llama-index
"""
import json
import logging
import os
from typing import List, Union, Generator, Iterator, Optional, Set

import chromadb
import requests
import sentence_transformers
from chromadb import Settings
from pydantic import BaseModel

log = logging.getLogger(__name__)


class Pipeline:

    class Valves(BaseModel):
        CHROMA_HTTP_HOST: Optional[str]
        CHROMA_HTTP_PORT: int
        CHROMA_HTTP_SSL: bool
        CHROMA_TENANT: str
        CHROMA_DATABASE: str
        CHROMA_DATA_PATH: str

    def __init__(self):
        self.name = 'Ollama RAG'
        self.rag_replacement = True
        self.valves = self.Valves(
            **{
                "CHROMA_HTTP_HOST": os.getenv("CHROMA_HTTP_HOST"),
                "CHROMA_HTTP_PORT": os.getenv("CHROMA_HTTP_PORT"),
                "CHROMA_HTTP_SSL": os.getenv("CHROMA_HTTP_SSL"),
                "CHROMA_TENANT": os.getenv("CHROMA_TENANT"),
                "CHROMA_DATABASE": os.getenv("CHROMA_DATABASE"),
                "CHROMA_DATA_PATH": os.getenv("CHROMA_DATA_PATH"),
            }
        )

        self.documents = None
        self.index = None
        self.chroma_client = None

    async def on_startup(self):
        # This function is called when the server is started.
        if self.valves.CHROMA_HTTP_HOST is not None and self.valves.CHROMA_HTTP_HOST != "":
            self.chroma_client = chromadb.HttpClient(
                host=self.valves.CHROMA_HTTP_HOST,
                port=self.valves.CHROMA_HTTP_PORT,
                ssl=self.valves.CHROMA_HTTP_SSL,
                tenant=self.valves.CHROMA_TENANT,
                database=self.valves.CHROMA_DATABASE,
                settings=Settings(allow_reset=True, anonymized_telemetry=False),
            )
        else:
            self.chroma_client = chromadb.PersistentClient(
                path=self.valves.CHROMA_DATA_PATH,
                settings=Settings(allow_reset=True, anonymized_telemetry=False),
                tenant=self.valves.CHROMA_TENANT,
                database=self.valves.CHROMA_DATABASE,
            )

    async def on_shutdown(self):
        # This function is called when the server is stopped.
        pass

    def pipe(
            self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        # This is where you can add your custom RAG pipeline.
        # Typically, you would retrieve relevant information from your knowledge base and synthesize it to generate a response.

        # Do the RAG part here
        context, citations = _extract_context(self.chroma_client, body, messages, user_message)
        _handle_context(context, body, messages)

        print(messages)
        print(user_message)

        # Forward the request to the Ollama server with retrieved context
        ollama_response = _call_ollama(body)
        if citations:
            yield f"data: {json.dumps({'citations': citations})}\n\n"
        for fragment in ollama_response:
            yield fragment


########################################################################################
# Utils
########################################################################################

def _extract_context(chroma_client, body, messages, user_message):
    context = ""
    citations = None
    if "docs" in body:
        rag_context, citations = _get_rag_context(
            chroma_client,
            docs=body["docs"],
            messages=messages,
            embedding_function=_get_embedding_function(),
            k=5,
            query=user_message
        )

        if rag_context:
            context += ("\n" if context != "" else "") + rag_context

        del body["docs"]

        log.debug(f"rag_context: {rag_context}, citations: {citations}")
    return context, citations


def _handle_context(context, body, messages):
    if context != "":
        system_prompt = _rag_template(
            context
        )

        print(system_prompt)

        body["messages"] = _add_or_update_system_message(
            f"\n{system_prompt}", messages
        )


def _query_doc(
        chroma_client,
        collection_name: str,
        query: str,
        embedding_function,
        k: int,
):
    try:
        collection = chroma_client.get_collection(name=collection_name)
        query_embeddings = embedding_function(query)

        result = collection.query(
            query_embeddings=[query_embeddings],
            n_results=k,
        )

        log.info(f"query_doc:result {result}")
        return result
    except Exception as e:
        raise e


def merge_and_sort_query_results(query_results, k, reverse=False):
    # Initialize lists to store combined data
    combined_distances = []
    combined_documents = []
    combined_metadatas = []

    for data in query_results:
        combined_distances.extend(data["distances"][0])
        combined_documents.extend(data["documents"][0])
        combined_metadatas.extend(data["metadatas"][0])

    # Create a list of tuples (distance, document, metadata)
    combined = list(zip(combined_distances, combined_documents, combined_metadatas))

    # Sort the list based on distances
    combined.sort(key=lambda x: x[0], reverse=reverse)

    # We don't have anything :-(
    if not combined:
        sorted_distances = []
        sorted_documents = []
        sorted_metadatas = []
    else:
        # Unzip the sorted list
        sorted_distances, sorted_documents, sorted_metadatas = zip(*combined)

        # Slicing the lists to include only k elements
        sorted_distances = list(sorted_distances)[:k]
        sorted_documents = list(sorted_documents)[:k]
        sorted_metadatas = list(sorted_metadatas)[:k]

    # Create the output dictionary
    result = {
        "distances": [sorted_distances],
        "documents": [sorted_documents],
        "metadatas": [sorted_metadatas],
    }

    return result


def _query_collection(
        chroma_client,
        collection_names: List[str] | Set[str],
        query: str,
        embedding_function,
        k: int,
):
    results = []
    for collection_name in collection_names:
        try:
            result = _query_doc(
                chroma_client=chroma_client,
                collection_name=collection_name,
                query=query,
                k=k,
                embedding_function=embedding_function,
            )
            results.append(result)
        except Exception as e:
            pass
    return merge_and_sort_query_results(results, k=k)


def _rag_template(context: str):
    return f"""
    Use the following context as your learned knowledge, inside <context></context> XML tags.
<context>
    {context}
</context>
    """


def _get_embedding_function():
    def embedding_function(query):
        transformer = sentence_transformers.SentenceTransformer(
            "sentence-transformers/all-MiniLM-L6-v2"
        )
        return transformer.encode(query).tolist()

    def generate_multiple(query, f):
        if isinstance(query, list):
            return [f(q) for q in query]
        else:
            return f(query)

    return lambda query: generate_multiple(query, embedding_function)


def _get_rag_context(
        chroma_client,
        docs,
        messages,
        embedding_function,
        k,
        query
):
    log.debug(f"docs: {docs} {messages} {embedding_function}")

    extracted_collections = []
    relevant_contexts = []

    for doc in docs:
        context = None

        collection_names = (
            doc["collection_names"]
            if doc["type"] == "collection"
            else [doc["collection_name"]]
        )

        collection_names = set(collection_names).difference(extracted_collections)
        if not collection_names:
            log.debug(f"skipping {doc} as it has already been extracted")
            continue

        try:
            if doc["type"] == "text":
                context = doc["content"]
            else:
                context = _query_collection(
                    chroma_client=chroma_client,
                    collection_names=collection_names,
                    query=query,
                    embedding_function=embedding_function,
                    k=k,
                )
        except Exception as e:
            log.exception(e)
            context = None

        if context:
            relevant_contexts.append({**context, "source": doc})

        extracted_collections.extend(collection_names)

    context_string = ""

    citations = []
    for context in relevant_contexts:
        try:
            if "documents" in context:
                context_string += "\n\n".join(
                    [text for text in context["documents"][0] if text is not None]
                )

                if "metadatas" in context:
                    citations.append(
                        {
                            "source": context["source"],
                            "document": context["documents"][0],
                            "metadata": context["metadatas"][0],
                        }
                    )
        except Exception as e:
            log.exception(e)

    context_string = context_string.strip()

    return context_string, citations


def _add_or_update_system_message(content: str, messages: List[dict]):
    """
    Adds a new system message at the beginning of the messages list
    or updates the existing system message at the beginning.

    :param msg: The message to be added or appended.
    :param messages: The list of message dictionaries.
    :return: The updated list of message dictionaries.
    """

    if messages and messages[0].get("role") == "system":
        messages[0]["content"] += f"{content}\n{messages[0]['content']}"
    else:
        # Insert at the beginning
        messages.insert(0, {"role": "system", "content": content})

    return messages


def _call_ollama(body):
    try:
        r = requests.post(
            url=f"http://localhost:11434/api/chat",
            json={**body, "model": "llama3:8b"},
            stream=True,
        )

        r.raise_for_status()

        if body["stream"]:
            return (json.loads(fragment)["message"]["content"] for fragment in r.iter_lines())
        else:
            return r.json()
    except Exception as e:
        return f"Error: {e}"
