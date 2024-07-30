"""
title: Presidio PII Redaction Pipeline
author: justinh-rahb
date: 2024-07-07
version: 0.1.0
license: MIT
description: A pipeline for redacting personally identifiable information (PII) using the Presidio library.
requirements: presidio-analyzer, presidio-anonymizer
"""

import os
from typing import List, Optional
from pydantic import BaseModel
from schemas import OpenAIChatMessage
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

class Pipeline:
    class Valves(BaseModel):
        pipelines: List[str] = ["*"]
        priority: int = 0
        enabled_for_admins: bool = False
        entities_to_redact: List[str] = [
            "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "US_SSN", 
            "CREDIT_CARD", "IP_ADDRESS", "US_PASSPORT", "LOCATION",
            "DATE_TIME", "NRP", "MEDICAL_LICENSE", "URL"
        ]
        language: str = "en"

    def __init__(self):
        self.type = "filter"
        self.name = "Presidio PII Redaction Pipeline"

        self.valves = self.Valves(
            **{
                "pipelines": os.getenv("PII_REDACT_PIPELINES", "*").split(","),
                "enabled_for_admins": os.getenv("PII_REDACT_ENABLED_FOR_ADMINS", "false").lower() == "true",
                "entities_to_redact": os.getenv("PII_REDACT_ENTITIES", ",".join(self.Valves().entities_to_redact)).split(","),
                "language": os.getenv("PII_REDACT_LANGUAGE", "en"),
            }
        )

        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()

    async def on_startup(self):
        print(f"on_startup:{__name__}")

    async def on_shutdown(self):
        print(f"on_shutdown:{__name__}")

    def redact_pii(self, text: str) -> str:
        results = self.analyzer.analyze(
            text=text,
            language=self.valves.language,
            entities=self.valves.entities_to_redact
        )

        anonymized_text = self.anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators={
                "DEFAULT": OperatorConfig("replace", {"new_value": "[REDACTED]"})
            }
        )

        return anonymized_text.text

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        print(f"pipe:{__name__}")
        print(body)
        print(user)

        if user is None or user.get("role") != "admin" or self.valves.enabled_for_admins:
            messages = body.get("messages", [])
            for message in messages:
                if message.get("role") == "user":
                    message["content"] = self.redact_pii(message["content"])

        return body
