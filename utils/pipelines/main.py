import uuid
import time

from typing import List
from schemas import OpenAIChatMessage

import inspect
from typing import get_type_hints, Literal, Tuple


def stream_message_template(model: str, message: str):
    return {
        "id": f"{model}-{str(uuid.uuid4())}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"content": message},
                "logprobs": None,
                "finish_reason": None,
            }
        ],
    }


def get_last_user_message(messages: List[dict]) -> str:
    for message in reversed(messages):
        if message["role"] == "user":
            if isinstance(message["content"], list):
                for item in message["content"]:
                    if item["type"] == "text":
                        return item["text"]
            return message["content"]
    return None


def get_last_assistant_message(messages: List[dict]) -> str:
    for message in reversed(messages):
        if message["role"] == "assistant":
            if isinstance(message["content"], list):
                for item in message["content"]:
                    if item["type"] == "text":
                        return item["text"]
            return message["content"]
    return None


def get_system_message(messages: List[dict]) -> dict:
    for message in messages:
        if message["role"] == "system":
            return message
    return None


def remove_system_message(messages: List[dict]) -> List[dict]:
    return [message for message in messages if message["role"] != "system"]


def pop_system_message(messages: List[dict]) -> Tuple[dict, List[dict]]:
    return get_system_message(messages), remove_system_message(messages)


def add_or_update_system_message(content: str, messages: List[dict]) -> List[dict]:
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


def doc_to_dict(docstring):
    lines = docstring.split("\n")
    description = lines[1].strip()
    param_dict = {}

    for line in lines:
        if ":param" in line:
            line = line.replace(":param", "").strip()
            param, desc = line.split(":", 1)
            param_dict[param.strip()] = desc.strip()
    ret_dict = {"description": description, "params": param_dict}
    return ret_dict


def get_tools_specs(tools) -> List[dict]:
    function_list = [
        {"name": func, "function": getattr(tools, func)}
        for func in dir(tools)
        if callable(getattr(tools, func)) and not func.startswith("__")
    ]

    specs = []

    for function_item in function_list:
        function_name = function_item["name"]
        function = function_item["function"]

        function_doc = doc_to_dict(function.__doc__ or function_name)
        specs.append(
            {
                "name": function_name,
                # TODO: multi-line desc?
                "description": function_doc.get("description", function_name),
                "parameters": {
                    "type": "object",
                    "properties": {
                        param_name: {
                            "type": param_annotation.__name__.lower(),
                            **(
                                {
                                    "enum": (
                                        param_annotation.__args__
                                        if hasattr(param_annotation, "__args__")
                                        else None
                                    )
                                }
                                if hasattr(param_annotation, "__args__")
                                else {}
                            ),
                            "description": function_doc.get("params", {}).get(
                                param_name, param_name
                            ),
                        }
                        for param_name, param_annotation in get_type_hints(
                            function
                        ).items()
                        if param_name != "return"
                    },
                    "required": [
                        name
                        for name, param in inspect.signature(
                            function
                        ).parameters.items()
                        if param.default is param.empty
                    ],
                },
            }
        )

    return specs
