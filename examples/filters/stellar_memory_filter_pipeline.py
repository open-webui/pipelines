"""
title: Stellar Memory Filter
author: sangjun0000
date: 2026-03-28
version: 2.0.0
license: MIT
description: A filter that automatically recalls relevant memories before each request and stores important responses using Stellar Memory — a local AI memory system with celestial mechanics metaphor.
requirements: pydantic, requests
"""

from typing import List, Optional
from pydantic import BaseModel
import requests


class Pipeline:
    class Valves(BaseModel):
        STM_URL: str = "http://localhost:21547"
        STM_PROJECT: str = ""
        RECALL_LIMIT: int = 5
        AUTO_REMEMBER: bool = True

    def __init__(self):
        self.name = "Stellar Memory"
        self.valves = self.Valves()

    async def on_startup(self):
        pass

    async def on_shutdown(self):
        pass

    def _project(self) -> str:
        return self.valves.STM_PROJECT.strip() or "default"

    def _extract_last_message(self, messages: list, role: str) -> Optional[str]:
        for msg in reversed(messages):
            if msg.get("role") == role:
                content = msg.get("content", "")
                if isinstance(content, list):
                    parts = [p.get("text", "") for p in content if p.get("type") == "text"]
                    return " ".join(parts).strip() or None
                return content.strip() or None
        return None

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        messages = body.get("messages", [])
        query = self._extract_last_message(messages, "user")
        if not query:
            return body

        try:
            resp = requests.get(
                f"{self.valves.STM_URL}/api/memories/search",
                params={"q": query, "limit": self.valves.RECALL_LIMIT, "project": self._project()},
                timeout=3,
            )
            resp.raise_for_status()
            data = resp.json()
            memories = data if isinstance(data, list) else data.get("memories", [])
        except Exception:
            return body

        if not memories:
            return body

        lines = ["[Stellar Memory — Relevant context]"]
        for m in memories:
            summary = m.get("summary") or m.get("content", "")[:80]
            mem_type = m.get("type", "context")
            lines.append(f"- {summary} ({mem_type})")
        injection = "\n".join(lines)

        if messages and messages[0].get("role") == "system":
            messages[0]["content"] = injection + "\n\n" + messages[0]["content"]
        else:
            messages.insert(0, {"role": "system", "content": injection})

        body["messages"] = messages
        return body

    async def outlet(self, body: dict, user: Optional[dict] = None) -> dict:
        if not self.valves.AUTO_REMEMBER:
            return body

        messages = body.get("messages", [])
        text = self._extract_last_message(messages, "assistant")
        if not text or len(text) < 100:
            return body

        try:
            requests.post(
                f"{self.valves.STM_URL}/api/memories",
                json={
                    "content": text[:500],
                    "summary": text[:80],
                    "type": "observation",
                    "tags": ["openwebui", "auto"],
                    "project": self._project(),
                },
                timeout=3,
            )
        except Exception:
            pass

        return body
