import json
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from agent import build_agent
from memory import create_checkpointer

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("flix")

_agent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agent
    checkpointer = await create_checkpointer()
    _agent = build_agent(checkpointer)
    logger.info("Flix agent ready")
    yield


app = FastAPI(lifespan=lifespan)


class ChatRequest(BaseModel):
    user_id: str
    session_id: str
    message: str


@app.post("/chat")
async def chat(req: ChatRequest):
    logger.info("session=%s user=%s | %s", req.session_id, req.user_id, req.message)
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
                    inputs = event.get("data", {}).get("input", {})
                    logger.debug("→ tool_start  %-30s  input=%s", event["name"], inputs)
                    yield {
                        "event": "tool_start",
                        "data": json.dumps({"tool": event["name"]}),
                    }

                elif kind == "on_tool_end":
                    output = event.get("data", {}).get("output", "")
                    preview = str(output)[:120].replace("\n", " ")
                    logger.debug("← tool_end    %-30s  output=%s", event["name"], preview)
                    yield {
                        "event": "tool_end",
                        "data": json.dumps({"tool": event["name"]}),
                    }

            logger.info("session=%s | done", req.session_id)
            yield {"event": "done", "data": json.dumps({"status": "complete"})}

        except Exception:
            logger.exception("session=%s | stream error", req.session_id)
            yield {"event": "error", "data": json.dumps({"message": "Something went wrong. Please try again."})}

    return EventSourceResponse(stream())
