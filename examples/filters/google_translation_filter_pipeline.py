"""
title: Google Translate Filter
author: SimonOriginal
date: 2024-06-28
version: 1.0
license: MIT
description: This pipeline integrates Google Translate for automatic translation of user and assistant messages 
without requiring an API key. It supports multilingual communication by translating based on specified source 
and target languages.
"""

import re
from typing import List, Optional
from schemas import OpenAIChatMessage
from pydantic import BaseModel
import requests
import os
import time
import asyncio
from functools import lru_cache

from utils.pipelines.main import get_last_user_message, get_last_assistant_message

class Pipeline:
    class Valves(BaseModel):
        pipelines: List[str] = []
        priority: int = 0
        source_user: Optional[str] = "auto"
        target_user: Optional[str] = "en"
        source_assistant: Optional[str] = "en"
        target_assistant: Optional[str] = "uk"

    def __init__(self):
        self.type = "filter"
        self.name = "Google Translate Filter"
        self.valves = self.Valves(
            **{
                "pipelines": ["*"],
            }
        )

        # Initialize translation cache
        self.translation_cache = {}
        self.code_blocks = []  # List to store code blocks

    async def on_startup(self):
        print(f"on_startup:{__name__}")
        pass

    async def on_shutdown(self):
        print(f"on_shutdown:{__name__}")
        pass

    async def on_valves_updated(self):
        pass

    # @lru_cache(maxsize=128)  # LRU cache to store translation results
    def translate(self, text: str, source: str, target: str) -> str:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": source,
            "tl": target,
            "dt": "t",
            "q": text,
        }
        
        try:
            r = requests.get(url, params=params)
            r.raise_for_status()
            result = r.json()
            translated_text = ''.join([sentence[0] for sentence in result[0]])
            return translated_text
        except requests.exceptions.RequestException as e:
            print(f"Network error: {e}")
            time.sleep(1)
            return self.translate(text, source, target)
        except Exception as e:
            print(f"Error translating text: {e}")
            return text

    def split_text_around_table(self, text: str) -> List[str]:
        table_regex = r'((?:^.*?\|.*?\n)+)(?=\n[^\|\s].*?\|)'
        matches = re.split(table_regex, text, flags=re.MULTILINE)

        if len(matches) > 1:
            return [matches[0], matches[1]]
        else:
            return [text, ""]

    def clean_table_delimiters(self, text: str) -> str:
        # Remove extra spaces from table delimiters
        return re.sub(r'(\|\s*-+\s*)+', lambda m: m.group(0).replace(' ', '-'), text)

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        print(f"inlet:{__name__}")

        messages = body["messages"]
        user_message = get_last_user_message(messages)

        print(f"User message: {user_message}")

        # Find and store code blocks
        code_block_regex = r'```[\s\S]+?```'
        self.code_blocks = re.findall(code_block_regex, user_message)
        # Replace code blocks with placeholders
        user_message_no_code = re.sub(code_block_regex, '__CODE_BLOCK__', user_message)

        parts = self.split_text_around_table(user_message_no_code)
        text_before_table, table_text = parts

        # Check translation cache for text before table
        translated_before_table = self.translation_cache.get(text_before_table)
        if translated_before_table is None:
            translated_before_table = self.translate(
                text_before_table,
                self.valves.source_user,
                self.valves.target_user,
            )
            self.translation_cache[text_before_table] = translated_before_table

        translated_user_message = translated_before_table + table_text

        # Clean table delimiters
        translated_user_message = self.clean_table_delimiters(translated_user_message)

        # Restore code blocks
        for code_block in self.code_blocks:
            translated_user_message = translated_user_message.replace('__CODE_BLOCK__', code_block, 1)

        print(f"Translated user message: {translated_user_message}")

        for message in reversed(messages):
            if message["role"] == "user":
                message["content"] = translated_user_message
                break

        body = {**body, "messages": messages}
        return body

    async def outlet(self, body: dict, user: Optional[dict] = None) -> dict:
        print(f"outlet:{__name__}")

        messages = body["messages"]
        assistant_message = get_last_assistant_message(messages)

        print(f"Assistant message: {assistant_message}")

        # Find and store code blocks
        code_block_regex = r'```[\s\S]+?```'
        self.code_blocks = re.findall(code_block_regex, assistant_message)
        # Replace code blocks with placeholders
        assistant_message_no_code = re.sub(code_block_regex, '__CODE_BLOCK__', assistant_message)

        parts = self.split_text_around_table(assistant_message_no_code)
        text_before_table, table_text = parts

        # Check translation cache for text before table
        translated_before_table = self.translation_cache.get(text_before_table)
        if translated_before_table is None:
            translated_before_table = self.translate(
                text_before_table,
                self.valves.source_assistant,
                self.valves.target_assistant,
            )
            self.translation_cache[text_before_table] = translated_before_table

        translated_assistant_message = translated_before_table + table_text

        # Clean table delimiters
        translated_assistant_message = self.clean_table_delimiters(translated_assistant_message)

        # Restore code blocks
        for code_block in self.code_blocks:
            translated_assistant_message = translated_assistant_message.replace('__CODE_BLOCK__', code_block, 1)

        print(f"Translated assistant message: {translated_assistant_message}")

        for message in reversed(messages):
            if message["role"] == "assistant":
                message["content"] = translated_assistant_message
                break

        body = {**body, "messages": messages}
        return body
