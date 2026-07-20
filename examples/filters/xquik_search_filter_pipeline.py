"""
title: Xquik Search Tools
author: Xquik
date: 2026-07-20
version: 1.1
license: MIT
description: Adds an opt-in Xquik tool for searching public X posts.
requirements: requests
"""

import os
from typing import Any, Literal

import requests

from blueprints.function_calling_blueprint import Pipeline as FunctionCallingBlueprint


def _read_positive_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default

    try:
        parsed_value = int(value)
    except ValueError:
        return default

    return parsed_value if parsed_value > 0 else default


class Pipeline(FunctionCallingBlueprint):
    class Valves(FunctionCallingBlueprint.Valves):
        XQUIK_API_KEY: str = ""
        XQUIK_BASE_URL: str = "https://xquik.com"
        MAX_RESULTS: int = 10
        REQUEST_TIMEOUT_SECONDS: int = 20

    class Tools:
        def __init__(self, pipeline: "Pipeline") -> None:
            self.pipeline = pipeline

        def search_x_posts(
            self,
            query: str,
            query_type: Literal["Latest", "Top"] = "Latest",
            limit: int = 5,
        ) -> str:
            """
            Search public X posts with Xquik.

            :param query: Search query. X search operators are supported.
            :param query_type: Sort order. Latest is chronological. Top is engagement-ranked.
            :param limit: Maximum number of posts to return.
            :return: A concise list of matching public posts.
            """
            api_key = self.pipeline.valves.XQUIK_API_KEY.strip()
            if not api_key:
                return (
                    "Xquik API key not set. Add XQUIK_API_KEY in the pipeline valves."
                )

            clean_query = query.strip()
            if not clean_query:
                return "Search query is required."

            safe_limit = max(1, min(limit, self.pipeline.valves.MAX_RESULTS, 25))
            timeout = max(
                1,
                min(self.pipeline.valves.REQUEST_TIMEOUT_SECONDS, 120),
            )
            try:
                response = requests.get(
                    f"{self.pipeline.valves.XQUIK_BASE_URL.rstrip('/')}/api/v1/x/tweets/search",
                    headers={"x-api-key": api_key},
                    params={
                        "q": clean_query,
                        "queryType": query_type,
                        "limit": safe_limit,
                    },
                    timeout=timeout,
                )
                response.raise_for_status()
                data = response.json()
            except (requests.RequestException, ValueError):
                return "Xquik search failed. Verify the pipeline valves and try again."

            if not isinstance(data, dict):
                return "Xquik returned an unexpected response."

            tweets = data.get("tweets", [])
            if not isinstance(tweets, list) or not tweets:
                return "No matching X posts found."

            lines = [
                self._format_tweet(tweet)
                for tweet in tweets[:safe_limit]
                if isinstance(tweet, dict)
            ]
            if not lines:
                return "No readable X posts found."

            return "\n\n".join(lines)

        def _format_tweet(self, tweet: dict[str, Any]) -> str:
            author = tweet.get("author")
            username = ""
            if isinstance(author, dict):
                username_value = author.get("username")
                if isinstance(username_value, str) and username_value:
                    username = f"@{username_value}: "

            text = tweet.get("text")
            tweet_text = text.strip() if isinstance(text, str) else "(no text)"

            details: list[str] = []
            tweet_id = tweet.get("id")
            if isinstance(tweet_id, str):
                details.append(f"ID: {tweet_id}")
            url = tweet.get("url")
            if isinstance(url, str):
                details.append(f"URL: {url}")

            suffix = "" if not details else f"\n{' | '.join(details)}"
            return f"{username}{tweet_text}{suffix}"

    def __init__(self) -> None:
        super().__init__()
        self.name = "Xquik Search Tools"
        self.valves = self.Valves(
            **{
                **self.valves.model_dump(),
                "pipelines": ["*"],
                "XQUIK_API_KEY": os.getenv("XQUIK_API_KEY", ""),
                "XQUIK_BASE_URL": os.getenv("XQUIK_BASE_URL", "https://xquik.com"),
                "MAX_RESULTS": _read_positive_int_env("XQUIK_MAX_RESULTS", 10),
                "REQUEST_TIMEOUT_SECONDS": _read_positive_int_env(
                    "XQUIK_REQUEST_TIMEOUT_SECONDS",
                    20,
                ),
            }
        )
        self.tools = self.Tools(self)


# Xquik is an independent third-party service. Not affiliated with X Corp.
# "Twitter" and "X" are trademarks of X Corp.
