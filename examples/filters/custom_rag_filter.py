from typing import List, Optional
from pydantic import BaseModel
from schemas import OpenAIChatMessage
from utils.pipelines.main import get_last_user_message, add_or_update_system_message
from blueprints.rag_utils import format_docs
from blueprints.prompts import accurate_rag_prompt
class Pipeline:
    class Valves(BaseModel):
        # List target pipeline ids (models) that this filter will be connected to.
        # If you want to connect this filter to all pipelines, you can set pipelines to ["*"]
        pipelines: List[str] = []

        # Assign a priority level to the filter pipeline.
        # The priority level determines the order in which the filter pipelines are executed.
        # The lower the number, the higher the priority.
        priority: int = 0

        # Add your custom parameters/configuration here e.g. API_KEY that you want user to configure etc.
        pass

    def __init__(self):
        self.chain = None
        self.type = "filter"
        self.name = "Filter"
        self.valves = self.Valves(**{"pipelines": ["*"]})

        pass
    def split_context(self, context):
        split_index = context.find("User question")
        system_prompt = context[:split_index].strip()
        user_question = context[split_index:].strip()
        user_split_index = user_question.find("<context>")
        f_system_prompt = str(system_prompt) + str(user_question[user_split_index:])
        return f_system_prompt
    
    async def on_startup(self):
        # This function is called when the server is started.
        print(f"on_startup:{__name__}")
        from typing import List
        import bs4
        from langchain.text_splitter import RecursiveCharacterTextSplitter
        from langchain_community.document_loaders import WebBaseLoader
        from langchain_community.vectorstores import Chroma
        from langchain_core.runnables import RunnablePassthrough
        from langchain_community.embeddings import HuggingFaceEmbeddings
        loader = WebBaseLoader(
        web_paths=("https://viblo.asia/p/graphrag-mot-su-nang-cap-moi-cua-rag-truyen-thong-chang-EoW4oXRBJml",),
        bs_kwargs=dict(
            parse_only=bs4.SoupStrainer(
                class_=("post-content", "post-title", "post-header")
            )
        ),
    )

        docs = loader.load()

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        splits = text_splitter.split_documents(docs)

        embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

        # Embed
        vectorstore = Chroma.from_documents(documents=splits, 
                                            embedding=embeddings) ##Replace the real Embedding in here

        retriever = vectorstore.as_retriever()
        
        self.chain = (
            {"context": retriever | format_docs, "question": RunnablePassthrough()}
            | accurate_rag_prompt
        )
        
        pass

    async def on_shutdown(self):
        # This function is called when the server is stopped.
        print(f"on_shutdown:{__name__}")
        pass
    

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        messages = body.get("messages", [])
        user_message = get_last_user_message(messages)
        rag_prompt = self.chain.invoke(user_message).text
        system_message = self.split_context(rag_prompt)
        body["messages"] = add_or_update_system_message(
                    system_message, messages
                )
        return body
    
    async def outlet(self, body : dict , user : Optional[dict]= None) -> dict :
        print(f"outlet:{__name__}")
        print(f"Outlet Body Input: {body}")
        return body