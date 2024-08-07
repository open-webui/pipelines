import os  # Standard library for interacting with the operating system
import copy  # Standard library for making shallow and deep copy operations
import asyncio  # Standard library for asynchronous I/O
from typing import List, Union, Generator, Iterator  # Typing module for type hints
from dotenv import load_dotenv  # Module to load environment variables from a .env file
from loguru import logger  # Third-party logging library
from pydantic import BaseModel  # Third-party library for data validation using Python type annotations
from groq import AsyncGroq  # Library for interacting with the Groq API

# Specify the path to the .env-groq file

# Load the environment variables from the specified file
load_dotenv()

# Configure logging
logger.add("pipeline-gorq.log", rotation="1 MB", retention="10 days", level="DEBUG")
logger.debug("Logging initialized")

# Define default values and model configuration using environment variables
GROQ_DEFAULT_MAX_TOKENS = int(os.getenv("GROQ_DEFAULT_MAX_TOKENS", "4096"))
GROQ_DEFAULT_TEMPERATURE = float(os.getenv("GROQ_DEFAULT_TEMPERATURE", "0.9"))
GROQ_DEFAULT_ROUNDS = int(os.getenv("GROQ_DEFAULT_ROUNDS", "1"))
GROQ_LAYERS = int(os.getenv("GROQ_LAYERS", "1"))
GROQ_AGENTS_PER_LAYER = int(os.getenv("GROQ_AGENTS_PER_LAYER", "3"))
GROQ_MULTITURN = os.getenv("GROQ_MULTITURN") == "True"

# Load model configurations from environment variables
GROQ_MODEL_AGGREGATE = os.getenv("GROQ_MODEL_AGGREGATE")
GROQ_MODEL_AGGREGATE_API_BASE = os.getenv("GROQ_MODEL_AGGREGATE_API_BASE")
GROQ_MODEL_AGGREGATE_API_KEY = os.getenv("GROQ_MODEL_AGGREGATE_API_KEY")

GROQ_MODEL_REFERENCE_1 = os.getenv("GROQ_MODEL_REFERENCE_1")
GROQ_MODEL_REFERENCE_1_API_BASE = os.getenv("GROQ_MODEL_REFERENCE_1_API_BASE")
GROQ_MODEL_REFERENCE_1_API_KEY = os.getenv("GROQ_MODEL_REFERENCE_1_API_KEY")

GROQ_MODEL_REFERENCE_2 = os.getenv("GROQ_MODEL_REFERENCE_2")
GROQ_MODEL_REFERENCE_2_API_BASE = os.getenv("GROQ_MODEL_REFERENCE_2_API_BASE")
GROQ_MODEL_REFERENCE_2_API_KEY = os.getenv("GROQ_MODEL_REFERENCE_2_API_KEY")

GROQ_MODEL_REFERENCE_3 = os.getenv("GROQ_MODEL_REFERENCE_3")
GROQ_MODEL_REFERENCE_3_API_BASE = os.getenv("GROQ_MODEL_REFERENCE_3_API_BASE")
GROQ_MODEL_REFERENCE_3_API_KEY = os.getenv("GROQ_MODEL_REFERENCE_3_API_KEY")

# Function to check if all required environment variables are loaded correctly
def check_env_variable(var, var_name):
    if var is None:
        logger.error(f"Environment variable {var_name} is not set.")
        raise ValueError(f"Environment variable {var_name} is not set.")
    logger.debug(f"{var_name}: {var}")
    return var

# Check and log model configurations
GROQ_MODEL_AGGREGATE = check_env_variable(GROQ_MODEL_AGGREGATE, "GROQ_MODEL_AGGREGATE")
GROQ_MODEL_AGGREGATE_API_BASE = check_env_variable(GROQ_MODEL_AGGREGATE_API_BASE, "GROQ_MODEL_AGGREGATE_API_BASE")
GROQ_MODEL_AGGREGATE_API_KEY = check_env_variable(GROQ_MODEL_AGGREGATE_API_KEY, "GROQ_MODEL_AGGREGATE_API_KEY")

GROQ_MODEL_REFERENCE_1 = check_env_variable(GROQ_MODEL_REFERENCE_1, "GROQ_MODEL_REFERENCE_1")
GROQ_MODEL_REFERENCE_1_API_BASE = check_env_variable(GROQ_MODEL_REFERENCE_1_API_BASE, "GROQ_MODEL_REFERENCE_1_API_BASE")
GROQ_MODEL_REFERENCE_1_API_KEY = check_env_variable(GROQ_MODEL_REFERENCE_1_API_KEY, "GROQ_MODEL_REFERENCE_1_API_KEY")

GROQ_MODEL_REFERENCE_2 = check_env_variable(GROQ_MODEL_REFERENCE_2, "GROQ_MODEL_REFERENCE_2")
GROQ_MODEL_REFERENCE_2_API_BASE = check_env_variable(GROQ_MODEL_REFERENCE_2_API_BASE, "GROQ_MODEL_REFERENCE_2_API_BASE")
GROQ_MODEL_REFERENCE_2_API_KEY = check_env_variable(GROQ_MODEL_REFERENCE_2_API_KEY, "GROQ_MODEL_REFERENCE_2_API_KEY")

GROQ_MODEL_REFERENCE_3 = check_env_variable(GROQ_MODEL_REFERENCE_3, "GROQ_MODEL_REFERENCE_3")
GROQ_MODEL_REFERENCE_3_API_BASE = check_env_variable(GROQ_MODEL_REFERENCE_3_API_BASE, "GROQ_MODEL_REFERENCE_3_API_BASE")
GROQ_MODEL_REFERENCE_3_API_KEY = check_env_variable(GROQ_MODEL_REFERENCE_3_API_KEY, "GROQ_MODEL_REFERENCE_3_API_KEY")

# Define the main pipeline class
class Pipeline:
    # Define the Valves class for API keys using Pydantic for data validation
    class Valves(BaseModel):
        GROQ_API_KEY_1: str = ""
        GROQ_API_KEY_2: str = ""
        GROQ_API_KEY_3: str = ""
        GROQ_API_KEY_4: str = ""

        class Config:
            arbitrary_types_allowed = True

    # Initialize the pipeline with model configurations and logging
    def __init__(self):
        self.name = "MOA Groq"
        self.valves = self.Valves(
            GROQ_API_KEY_1=os.getenv("GROQ_API_KEY_1"),
            GROQ_API_KEY_2=os.getenv("GROQ_API_KEY_2"),
            GROQ_API_KEY_3=os.getenv("GROQ_API_KEY_3"),
            GROQ_API_KEY_4=os.getenv("GROQ_API_KEY_4"),
        )
        self.model_aggregate = {
            "name": GROQ_MODEL_AGGREGATE,
            "api_base": GROQ_MODEL_AGGREGATE_API_BASE,
            "api_key": GROQ_MODEL_AGGREGATE_API_KEY,
        }
        self.reference_models = [
            {
                "name": GROQ_MODEL_REFERENCE_1,
                "api_base": GROQ_MODEL_REFERENCE_1_API_BASE,
                "api_key": GROQ_MODEL_REFERENCE_1_API_KEY,
            },
            {
                "name": GROQ_MODEL_REFERENCE_2,
                "api_base": GROQ_MODEL_REFERENCE_2_API_BASE,
                "api_key": GROQ_MODEL_REFERENCE_2_API_KEY,
            },
            {
                "name": GROQ_MODEL_REFERENCE_3,
                "api_base": GROQ_MODEL_REFERENCE_3_API_BASE,
                "api_key": GROQ_MODEL_REFERENCE_3_API_KEY,
            },
        ]
        self.current_model_index = 0  # Index to keep track of the current reference model
        self.client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
        self.messages = []  # Initialize an empty list to store conversation history

        logger.debug(f"Pipeline initialized with models: {self.reference_models}")

    # Asynchronous function to handle startup tasks
    async def on_startup(self):
        logger.info(f"on_startup: {self.name}")

    # Asynchronous function to handle shutdown tasks
    async def on_shutdown(self):
        logger.info(f"on_shutdown: {self.name}")

    # Asynchronous function to make API calls to the Groq API
    async def make_api_call(self, url, headers, data):
        try:
            logger.info(f">>>> Making API call to {url} with data: {data}")
            response = await self.client.chat.completions.create(
                messages=data["messages"],
                model=data["model"],
                max_tokens=data["max_tokens"],
                temperature=data["temperature"],
                stream=data.get("stream", False),
            )
            logger.info(f"Response received: {response}")
            return response
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return None

    # Asynchronous function to generate responses using a specific model
    async def generate_together(self, model_info, messages, max_tokens=GROQ_DEFAULT_MAX_TOKENS, temperature=GROQ_DEFAULT_TEMPERATURE):
        logger.debug(f"generate_together called with model: {model_info['name']}, messages: {messages}, max_tokens: {max_tokens}, temperature: {temperature}")

        url = f"{model_info['api_base']}/chat/completions"

        headers = {
            "Authorization": f"Bearer {model_info['api_key']}",
            "Content-Type": "application/json"
        }
        data = {
            "model": model_info["name"],
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True
        }

        logger.debug(f"Request data: {data}")

        attempts = 3  # Number of retry attempts
        while attempts > 0:
            logger.info(f"Sending request to {url} for model {model_info['name']}")

            response = await self.make_api_call(url, headers, data)
            if response:
                try:
                    content = ""
                    async for chunk in response:
                        if chunk.choices[0].delta.content is not None:
                            content += chunk.choices[0].delta.content
                    return content
                except AttributeError:
                    logger.warning(f"Retrying API call... Attempts left: {attempts-1}")
                    attempts -= 1
                    await asyncio.sleep(5)

        logger.error(f"Failed to get a response from model {model_info['name']} after multiple attempts.")
        return None

    # Asynchronous function to call reference models in parallel
    async def call_reference_models_parallel(self, messages):
        responses = []
        tasks = []
        for model in self.reference_models:
            logger.info(f"Using reference model: {model['name']} with API base: {model['api_base']} and API key: {model['api_key']}")
            tasks.append(asyncio.create_task(self.generate_together(model, messages)))
        
        results = await asyncio.gather(*tasks)
        for result in results:
            if result:
                responses.append(result)
        return responses

    # Function to rotate the current reference model
    def rotate_agents(self):
        self.current_model_index = (self.current_model_index + 1) % len(self.reference_models)

    # Function to aggregate responses from reference models
    def aggregate_responses(self, responses: List[str]) -> str:
        aggregated_response = "\n".join(responses)
        return aggregated_response

    # Asynchronous function to call the aggregate model with aggregated responses
    async def call_aggregator_model(self, aggregated_responses, messages):
        aggregated_message = [{"role": "user", "content": aggregated_responses}]
        final_response = await self.generate_together(self.model_aggregate, aggregated_message)
        return final_response

    # Function to inject references into messages
    def inject_references_to_messages(self, messages, references):
        messages = copy.deepcopy(messages)

        system_message = "You have been provided with a set of responses from various open-source models to the latest user query. Your task is to synthesize these responses into a single, high-quality response. It is crucial to critically evaluate the information provided in these responses, recognizing that some of it may be biased or incorrect. Your response should not simply replicate the given answers but should offer a refined, accurate, and comprehensive reply to the instruction. Ensure your response is well-structured, coherent, and adheres to the highest standards of accuracy and reliability. Remember to answer same as the user query's languages\n\nResponses from models:"

        for i, reference in enumerate(references):
            system_message += f"\n{i+1}. {reference}"

        if messages[0]["role"] == "system":
            messages[0]["content"] += "\n\n" + system_message
        else:
            messages = [{"role": "system", "content": system_message}] + messages

        return messages

    # Asynchronous function to generate responses with references
    async def generate_with_references(self, model_info, messages, references=[], max_tokens=GROQ_DEFAULT_MAX_TOKENS, temperature=GROQ_DEFAULT_TEMPERATURE):
        if len(references) > 0:
            messages = self.inject_references_to_messages(messages, references)

        logger.info(f"Generating with references for model {model_info['name']}")
        return await self.generate_together(model_info, messages=messages, temperature=temperature, max_tokens=max_tokens)

    # Asynchronous function to process a single item using a specific model
    async def process_fn(self, item, model_info, temperature=GROQ_DEFAULT_TEMPERATURE, max_tokens=GROQ_DEFAULT_MAX_TOKENS):
        messages = item["instruction"]

        logger.info(f"Processing with instruction {messages} using model {model_info['name']}")

        response = await self.generate_together(model_info, messages, max_tokens, temperature)
        if not response:
            raise ValueError(f"No response received from model {model_info['name']}")

        logger.info(f"Finished querying {model_info['name']}. Output: {response[:20]}")

        return {"output": response}

    # Asynchronous function to process a layer of models
    async def process_layer(self, data, temperature=GROQ_DEFAULT_TEMPERATURE, max_tokens=GROQ_DEFAULT_MAX_TOKENS):
        logger.info(f"Processing layer with {len(self.reference_models)} agents")
        responses = []
        for i in range(len(self.reference_models)):
            model_info = self.reference_models[self.current_model_index]
            self.rotate_agents()  # Rotate agents after each call
            logger.info(f"Agent {i+1}: Using model {model_info['name']}")
            response = await self.process_fn(
                {"instruction": data["instruction"][i]},
                model_info=model_info,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            responses.append(response["output"])

        return responses

    # Asynchronous function to run the entire pipeline
    async def run_pipeline(self, user_message, temperature=GROQ_DEFAULT_TEMPERATURE, max_tokens=GROQ_DEFAULT_MAX_TOKENS, rounds=GROQ_DEFAULT_ROUNDS, multi_turn=GROQ_MULTITURN):
        data = {
            "instruction": [[] for _ in range(len(self.reference_models))],
            "model_info": self.reference_models,
        }

        if multi_turn:
            for i in range(len(self.reference_models)):
                data["instruction"][i].append({"role": "user", "content": user_message})
        else:
            data["instruction"] = [[{"role": "user", "content": user_message}]] * len(self.reference_models)

        self.messages.append({"role": "user", "content": user_message})  # Append the user message to the conversation history

        for i_round in range(rounds):
            logger.info(f"Starting round {i_round + 1} of processing.")

            responses = await self.process_layer(data, temperature, max_tokens)

            logger.info(f"Responses after Round {i_round + 1}:")
            for i, response in enumerate(responses):
                logger.info(f"Model {self.reference_models[i]['name']}: {response[:50]}...")

        logger.info("Aggregating results & querying the aggregate model...")

        aggregated_responses = self.aggregate_responses(responses)
        output = await self.generate_with_references(
            model_info=self.model_aggregate,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=self.messages,  # Use the conversation history
            references=aggregated_responses,
        )

        logger.info(f"Final answer from {self.model_aggregate['name']}")
        logger.info("Output received from generate_with_references:")
        logger.info(output)

        if multi_turn:
            for i in range(len(self.reference_models)):
                data["instruction"][i].append({"role": "assistant", "content": output})

        self.messages.append({"role": "assistant", "content": output})  # Append the assistant's response to the conversation history

        return output

    # Function to process user messages and run the pipeline
    def pipe(self, user_message: str, model_id: str = None, messages: List[dict] = None, body: dict = None) -> Union[str, Generator, Iterator]:
        logger.info(f"pipe called with user_message: {user_message}")
        logger.info(f"pipe called with model_id: {model_id}")
        logger.info(f"pipe called with messages: {messages}")
        logger.info(f"pipe called with body: {body}")

        final_output = asyncio.run(self.run_pipeline(user_message))
        return final_output

# Main function to initialize and run the pipeline
# def main():
#     pipeline = Pipeline()
#     result = pipeline.pipe("Top things to do in NYC", model_id="moa_groq_manifold")
#     print(result)

# if __name__ == "__main__":
#     main()
