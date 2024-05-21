from typing import List, Union, Generator
from schemas import OpenAIChatMessage
import os
import asyncio

from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.core import VectorStoreIndex, Settings
from llama_index.readers.github import GithubRepositoryReader, GithubClient

Settings.embed_model = OllamaEmbedding(
    model_name="nomic-embed-text",
    base_url="http://localhost:11434",
)
Settings.llm = Ollama(model="llama3")


index = None
documents = None


def get_response(
    user_message: str, messages: List[OpenAIChatMessage]
) -> Union[str, Generator]:
    # This is where you can add your custom RAG pipeline.
    # Typically, you would retrieve relevant information from your knowledge base and synthesize it to generate a response.

    print(messages)
    print(user_message)

    query_engine = index.as_query_engine(streaming=True)
    response = query_engine.query(user_message)

    return response.response_gen


async def on_startup():
    global index, documents

    github_token = os.environ.get("GITHUB_TOKEN")
    owner = "open-webui"
    repo = "plugin-server"
    branch = "main"

    github_client = GithubClient(github_token=github_token, verbose=True)

    reader = GithubRepositoryReader(
        github_client=github_client,
        owner=owner,
        repo=repo,
        use_parser=False,
        verbose=False,
        filter_file_extensions=(
            [
                ".png",
                ".jpg",
                ".jpeg",
                ".gif",
                ".svg",
                ".ico",
                "json",
                ".ipynb",
            ],
            GithubRepositoryReader.FilterType.EXCLUDE,
        ),
    )

    loop = asyncio.new_event_loop()

    reader._loop = loop

    try:
        # Load data from the branch
        documents = await asyncio.to_thread(reader.load_data, branch=branch)
        index = VectorStoreIndex.from_documents(documents)
    finally:
        loop.close()

    print(documents)
    print(index)


async def on_shutdown():
    # This function is called when the pipeline is stopped.
    pass
