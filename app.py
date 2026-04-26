import json
from contextlib import asynccontextmanager
from fastapi import FastAPI
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from agent import build_agent
from memory import create_checkpointer

_agent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agent
    checkpointer = await create_checkpointer()
    _agent = build_agent(checkpointer)
    yield


app = FastAPI(lifespan=lifespan)


class ChatRequest(BaseModel):
    user_id: str
    session_id: str
    message: str


@app.post("/chat")
async def chat(req: ChatRequest):
    config = {"configurable": {"thread_id": req.session_id}}

    async def stream():
        try:
            async for event in _agent.astream_events(
                {"messages": [{"role": "user", "content": req.message}]},
                config=config,
                version="v2",
            ):
                kind = event["event"]

                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    content = chunk.content if isinstance(chunk.content, str) else ""
                    if content:
                        yield {"event": "token", "data": json.dumps({"content": content})}

                elif kind == "on_tool_start":
                    yield {
                        "event": "tool_start",
                        "data": json.dumps({"tool": event["name"]}),
                    }

                elif kind == "on_tool_end":
                    yield {
                        "event": "tool_end",
                        "data": json.dumps({"tool": event["name"]}),
                    }

            yield {"event": "done", "data": json.dumps({"status": "complete"})}

        except Exception:
            yield {"event": "error", "data": json.dumps({"message": "Something went wrong. Please try again."})}

    return EventSourceResponse(stream())
