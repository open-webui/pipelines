"""
title: Wikipedia Article Retrieval
author: Unknown
author_url: Unknown
git_url: https://github.com/open-webui/pipelines/blob/main/examples/pipelines/integrations/wikipedia_pipeline.py
description: Wikipedia Search and Return
required_open_webui_version: 0.4.3
requirements: wikipedia
version: 0.4.3
licence: MIT
"""


from typing import List, Union, Generator, Iterator
from pydantic import BaseModel, Field
import wikipedia
import requests
import os
from datetime import datetime
import time
import re

from logging import getLogger
logger = getLogger(__name__)
logger.setLevel("DEBUG")


class Pipeline:
    class Valves(BaseModel):
        # OPENAI_API_KEY: str = Field(default="", description="OpenAI API key")
        RATE_LIMIT: int = Field(default=5, description="Rate limit for the pipeline")
        WORD_LIMIT: int = Field(default=300, description="Word limit when getting page summary")
        WIKIPEDIA_ROOT: str = Field(default="https://en.wikipedia.org/wiki", description="Wikipedia root URL")

    def __init__(self):
        # Optionally, you can set the id and name of the pipeline.
        # Best practice is to not specify the id so that it can be automatically inferred from the filename, so that users can install multiple versions of the same pipeline.
        # The identifier must be unique across all pipelines.
        # The identifier must be an alphanumeric string that can include underscores or hyphens. It cannot contain spaces, special characters, slashes, or backslashes.
        # self.id = "wiki_pipeline"
        self.name = "Wikipedia Pipeline"

        # Initialize valve paramaters
        self.valves = self.Valves(
            **{k: os.getenv(k, v.default) for k, v in self.Valves.model_fields.items()}
        )

    async def on_startup(self):
        # This function is called when the server is started.
        logger.debug(f"on_startup:{self.name}")
        pass

    async def on_shutdown(self):
        # This function is called when the server is stopped.
        logger.debug(f"on_shutdown:{self.name}")
        pass

    def rate_check(self, dt_start: datetime):
        """
        Check time, sleep if not enough time has passed for rate
        
        Args:
            dt_start (datetime): Start time of the operation
        Returns:
            bool: True if sleep was done
        """
        dt_end = datetime.now()
        time_diff = (dt_end - dt_start).total_seconds()
        time_buffer = (1 / self.valves.RATE_LIMIT)
        if time_diff >= time_buffer:    # no need to sleep
            return False
        time.sleep(time_buffer - time_diff)
        return True

    def pipe(
        self, 
        user_message: str, 
        model_id: str, 
        messages: List[dict], 
        body: dict
    ) -> Union[str, Generator, Iterator]:
        """
        Main pipeline function. Performs wikipedia article lookup by query
        and returns the summary of the first article.
        """
        logger.debug(f"pipe:{self.name}")

        # Check if title generation is requested
        # as of 12/28/24, these were standard greetings
        if ("broad tags categorizing" in user_message.lower()) \
                or ("Create a concise" in user_message.lower()):
            # ## Create a concise, 3-5 word title with
            # ## Task:\nGenerate 1-3 broad tags categorizing the main themes
            logger.debug(f"Title Generation (aborted): {user_message}")
            return "(title generation disabled)"

        logger.info(f"User Message: {user_message}")
        # logger.info(f"Messages: {messages}")
        # [{'role': 'user', 'content': 'history of ibm'}]
        
        # logger.info(f"Body: {body}")
        #  {'stream': True, 'model': 'wikipedia_pipeline', 
        #   'messages': [{'role': 'user', 'content': 'history of ibm'}], 
        #   'user': {'name': 'User', 'id': '235a828f-84a3-44a0-b7af-721ee8be6571', 
        #            'email': 'admin@localhost', 'role': 'admin'}}

        dt_start = datetime.now()
        multi_part = False
        streaming = body.get("stream", False)
        logger.warning(f"Stream: {streaming}")
        context = ""

        # examples from https://pypi.org/project/wikipedia/
        # new addition - ability to include multiple topics with a semicolon
        for query in user_message.split(';'):
            self.rate_check(dt_start)
            query = query.strip()

            if multi_part:
                if streaming:
                    yield "---\n"
                else:
                    context += "---\n"
            if body.get("stream", True):
                yield from self.stream_retrieve(query, dt_start)
            else:
                for chunk in self.stream_retrieve(query, dt_start):
                    context += chunk
            multi_part = True
        
        if not streaming:
            return context if context else "No information found"


    def stream_retrieve(
            self, query:str, dt_start: datetime,
        ) -> Generator:
        """
        Retrieve the wikipedia page for the query and return the summary.  Return a generator
        for streaming responses but can also be iterated for a single response.
        """

        re_query = re.compile(r"[^0-9A-Z]", re.IGNORECASE)
        re_rough_word = re.compile(r"[\w]+", re.IGNORECASE)

        titles_found = None
        try:
            titles_found = wikipedia.search(query)
            # r = requests.get(
            #     f"https://en.wikipedia.org/w/api.php?action=opensearch&search={query}&limit=1&namespace=0&format=json"
            # )
            logger.info(f"Query: {query}, Found: {titles_found}")
        except Exception as e:
            logger.error(f"Search Error: {query} -> {e}")
            yield f"Page Search Error: {query}"

        if titles_found is None or not titles_found:   # no results
            yield f"No information found for '{query}'"
            return

        self.rate_check(dt_start)

        # if context: # add separator if multiple topics
        #     context += "---\n"
        try:
            title_check = titles_found[0]
            wiki_page = wikipedia.page(title_check, auto_suggest=False)   # trick! don't auto-suggest
        except wikipedia.exceptions.DisambiguationError as e:
            str_error = str(e).replace("\n", ", ")
            str_error = f"## Disambiguation Error ({query})\n* Status: {str_error}"
            logger.error(str_error)
            yield str_error + "\n"
            return
        except wikipedia.exceptions.RedirectError as e:
            str_error = str(e).replace("\n", ", ")
            str_error = f"## Redirect Error ({query})\n* Status: {str_error}"
            logger.error(str_error)
            yield str_error + "\n"
            return
        except Exception as e:
            if titles_found:
                str_error = f"## Page Retrieve Error ({query})\n* Found Topics (matched '{title_check}') {titles_found}"
                logger.error(f"{str_error} -> {e}")
            else:
                str_error = f"## Page Not Found ({query})\n* Unknown error"
                logger.error(f"{str_error} -> {e}")
            yield str_error + "\n"
            return

        # found a page / section
        logger.info(f"Page Sections[{query}]: {wiki_page.sections}")
        yield f"## {title_check}\n"

        # flatten internal links
        # link_md = [f"[{x}]({self.valves.WIKIPEDIA_ROOT}/{re_query.sub('_', x)})" for x in wiki_page.links[:10]]
        # yield "* Links (first 30): " + ",".join(link_md) + "\n"

        # add the textual summary
        summary_full = wiki_page.summary
        word_positions = [x.start() for x in re_rough_word.finditer(summary_full)]
        if len(word_positions) > self.valves.WORD_LIMIT:
            yield summary_full[:word_positions[self.valves.WORD_LIMIT]] + "...\n"
        else:
            yield summary_full + "\n"

        # the more you know! link to further reading        
        yield "### Learn More" + "\n"
        yield f"* [Read more on Wikipedia...]({wiki_page.url})\n"

        # also spit out the related topics from search
        link_md = [f"[{x}]({self.valves.WIKIPEDIA_ROOT}/{re_query.sub('_', x)})" for x in titles_found]
        yield f"* Related topics: {', '.join(link_md)}\n"

        # throw in the first image for good measure
        if wiki_page.images:
            yield f"\n![Image: {title_check}]({wiki_page.images[0]})\n"

        return