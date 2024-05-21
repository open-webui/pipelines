from typing import List
from pydantic import BaseModel, ConfigDict


class OpenAIChatMessage(BaseModel):
    role: str
    content: str

    model_config = ConfigDict(extra="allow")


class OpenAIChatCompletionForm(BaseModel):
    stream: bool = True
    model: str
    messages: List[OpenAIChatMessage]

    model_config = ConfigDict(extra="allow")
