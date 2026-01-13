# -*- coding: utf-8 -*-
"""
DBGPT Integration Pipeline for OpenWebUI

This pipeline enables OpenWebUI to integrate with a self-hosted DBGPT service
as an external AI backend. It is designed as a blocking-only pipeline for
enterprise-grade stability, demo scenarios, and text-to-SQL use cases.

Key features:
- Blocking request mode (no streaming exposed to OpenWebUI)
- Robust exception shielding
- Output normalization for mixed DBGPT responses (text / chart-view / think)
"""

from typing import List, Union, Optional
import json
import re
import requests
from pprint import pprint


class Pipeline:
    def __init__(self):
        # Pipeline display name
        self.name = "DBGPT Integration Pipeline"

        # ===== DBGPT configuration =====
        # Users can modify these values according to their deployment
        self.dbgpt_api_url = "http://localhost:5670/api/v1/chat/completions"
        self.app_code = "your_dbgpt_app_code"
        self.model_name = "Qwen3-32B"
        self.domain = "default_domain"

        # Behavior flags
        self.debug = False
        self.timeout = 300  # seconds

    # ---------------------------------------------------------------------
    # Lifecycle hooks
    # ---------------------------------------------------------------------

    async def on_startup(self):
        print(f"[{self.name}] startup")

    async def on_shutdown(self):
        print(f"[{self.name}] shutdown")

    # ---------------------------------------------------------------------
    # Optional inlet / outlet hooks (kept for consistency with examples)
    # ---------------------------------------------------------------------

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        if self.debug:
            print("[inlet] body:")
            pprint(body)
            print("[inlet] user:")
            pprint(user)
        return body

    async def outlet(self, body: dict, user: Optional[dict] = None) -> dict:
        if self.debug:
            print("[outlet] body:")
            pprint(body)
            print("[outlet] user:")
            pprint(user)
        return body

    # ---------------------------------------------------------------------
    # Core pipeline entry
    # ---------------------------------------------------------------------

    def pipe(
        self,
        user_message: str,
        model_id: str,
        messages: List[dict],
        body: dict,
    ) -> Union[str]:
        """
        Blocking-only pipeline.

        Although DBGPT itself may support streaming internally,
        this pipeline always returns a finalized response to OpenWebUI
        to ensure stability and consistent error handling.
        """

        user_message = self._sanitize_user_message(user_message)

        if self.debug:
            print(f"[pipe] model_id: {model_id}")
            print(f"[pipe] user_message: {user_message}")

        payload = {
            "app_code": self.app_code,
            "conv_uid": self._get_conv_uid(body),
            "chat_mode": "chat_with_db_execute",
            "model_name": self.model_name,
            "user_input": user_message,
            "temperature": 0.2,
            "max_new_tokens": 3000,
            "select_param": self.domain,
        }

        raw_answer = ""

        try:
            response = requests.post(
                self.dbgpt_api_url,
                json=payload,
                stream=False,
                timeout=self.timeout,
            )

            response.raise_for_status()

            for line in response.iter_lines():
                if not line:
                    continue

                decoded = line.decode("utf-8").strip()
                if not decoded.startswith("data: "):
                    continue

                data = decoded[6:]
                if data == "[DONE]":
                    break

                try:
                    chunk = json.loads(data)
                    message = (
                        chunk.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content")
                    )
                    if message:
                        raw_answer += message
                except Exception:
                    # Silently ignore malformed chunks
                    continue

        except Exception as exc:
            print(f"[{self.name}] DBGPT request failed:", exc)
            return "Sorry, the system failed to complete the query."

        return self._clean_answer(raw_answer)

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------

    def _get_conv_uid(self, body: dict) -> Optional[str]:
        """
        Conversation UID strategy:
        - Same OpenWebUI user → same DBGPT conversation
        """
        if not body:
            return None

        user = body.get("user")
        if user and user.get("id"):
            return f"dbgpt-user-{user['id']}"
        return None

    def _sanitize_user_message(self, text: str) -> str:
        """
        Extract the last USER message from OpenWebUI chat history.
        """
        if not text:
            return ""

        marker = "### Chat History:"
        if marker in text:
            text = text.split(marker, 1)[1]

        match = re.search(r"<chat_history>([\s\S]*?)</chat_history>", text)
        if not match:
            return text.strip().splitlines()[0]

        history = match.group(1)
        user_msgs = re.findall(r"USER:\s*(.+)", history)

        return user_msgs[-1].strip() if user_msgs else ""

    def _clean_answer(self, text: str) -> str:
        """
        Normalize DBGPT mixed output:
        - Remove internal JSON blocks
        - Remove <think> tags
        - Preserve <chart-view /> if present
        """
        if not text:
            return "No result was returned."

        chart_match = re.search(r"<chart-view[\s\S]*?/>", text)
        chart_html = chart_match.group(0) if chart_match else ""

        text = re.sub(r"<chart-view[\s\S]*?/>", "", text)
        text = re.sub(r"^\s*\{[\s\S]*?\}\s*", "", text)
        text = re.sub(r"<think>[\s\S]*?</think>", "", text)

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        result = lines[-1] if lines else "Query completed."

        return f"{result}\n{chart_html}" if chart_html else result
