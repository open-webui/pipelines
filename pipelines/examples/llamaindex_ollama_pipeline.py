from typing import List, Union, Generator
from schemas import OpenAIChatMessage


documents = None
index = None


def get_response(
    user_message: str, messages: List[OpenAIChatMessage]
) -> Union[str, Generator]:
    # This is where you can add your custom RAG pipeline.
    # Typically, you would retrieve relevant information from your knowledge base and synthesize it to generate a response.

    print(messages)
    print(user_message)

    query_engine = index.as_query_engine(streaming=True)
    response = query_engine.query(user_message)

    print(response)

    return response.response_gen


async def on_startup():
    from llama_index.embeddings.ollama import OllamaEmbedding
    from llama_index.llms.ollama import Ollama
    from llama_index.core import Settings, VectorStoreIndex, SimpleDirectoryReader

    Settings.embed_model = OllamaEmbedding(
        model_name="nomic-embed-text",
        base_url="http://localhost:11434",
    )
    Settings.llm = Ollama(model="llama3")

    # This function is called when the server is started.
    global documents, index

    documents = SimpleDirectoryReader("./data").load_data()
    index = VectorStoreIndex.from_documents(documents)

    pass


async def on_shutdown():
    # This function is called when the server is stopped.
    pass
