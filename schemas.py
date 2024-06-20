from typing import List, Union, Optional
from pydantic import BaseModel, RootModel, ConfigDict

class ImageContent(BaseModel):
    type: str
    image_url: dict

class TextContent(BaseModel):
    type: str
    text: str

class MessageContent(RootModel):
    root: Union[TextContent, ImageContent]

class OpenAIChatMessage(BaseModel):
    role: str
    content: Union[str, List[MessageContent]]

    model_config = ConfigDict(extra="allow")

class OpenAIChatCompletionForm(BaseModel):
    stream: bool = True
    model: str
    messages: List[OpenAIChatMessage]

    model_config = ConfigDict(extra="allow")

class FilterForm(BaseModel):
    body: dict
    user: Optional[dict] = None
    model_config = ConfigDict(extra="allow")