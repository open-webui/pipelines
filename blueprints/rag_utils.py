from langchain_core.documents import Document
from typing import List
def format_docs(docs: List[Document]) -> str:
    """Convert Documents to a single string.:"""
    formatted = [
        f"Article Source: {doc.metadata}\nArticle Content: {doc.page_content}"
        for doc in docs
    ]
    return "\n" + "\n".join(formatted)