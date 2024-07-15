To use `LangGraph` or `LangChain` in openwebui-pipelines, we can
1. Build a chain or agent through `LangGraph` or `LangChain`, as described in [langgraph_agent.py](./langgraph_agent.py)
2. Create a web service for chain or agent through `FastAPI`, as described in [fastapi_server.py](./fastapi_server.py)
3. Call FastAPI API in pipelines to get chain or agent results through `requests`, as described in [pipelines.py](./pipelines.py)