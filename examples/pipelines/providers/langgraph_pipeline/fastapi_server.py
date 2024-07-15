from langgraph_agent import graph, State

from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="API for openwebui-pipelines",
    description="API for openwebui-pipelines",
    )

@app.post("/openwebui-pipelines/api")
async def main(inputs: State):
    async def event_stream():
        async for event in graph.astream_events(input = inputs
                                                ,version="v2"
                                                ):
            kind = event["event"]
            if  kind == "on_chat_model_stream" or kind=="on_chain_stream":
                content = event["data"]["chunk"]
                if content:
                    yield content

    return StreamingResponse(event_stream(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8510)