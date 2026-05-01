# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the dev server (port 8081)
./start.sh
# Or manually:
source venv/bin/activate
uvicorn app:app --reload --port 8081

# Install dependencies
pip install -r requirements.txt
```

There are no tests in this project.

## Architecture

FastAPI service that exposes `POST /chat` as a Server-Sent Events stream. A single LangGraph ReAct agent (named "Flix") is built at startup in `app.py` lifespan, shared across all requests, and invoked per request with a `thread_id` derived from `session_id`.

**Request flow:**

```
POST /chat (app.py)
  → _agent.astream_events(...)      # LangGraph ReAct loop
      → tools.py functions          # async HTTP calls to Spring Boot
      → memory checkpointer         # Redis or InMemorySaver
  → SSE stream: token / tool_start / tool_end / done / error
```

**Module responsibilities:**

- `app.py` — FastAPI app, lifespan agent initialization, SSE streaming logic. `agent_chat.py` is just a re-export alias for `uvicorn agent_chat:app`.
- `agent.py` — Assembles the LangGraph agent from `ChatOpenAI` + tools + checkpointer + system prompt. The system prompt enforces that Flix never invents data — always calls tools.
- `tools.py` — Five `@tool`-decorated async functions. All share `_spring_get()` which creates a fresh `httpx.AsyncClient` per call. Format helpers (`_fmt_*`) convert raw JSON to plain-text strings before returning to the LLM.
- `memory.py` — Tries to connect to Redis (`AsyncRedisSaver`); silently falls back to `InMemorySaver` on any exception. Session memory is keyed by `session_id` from the request body.
- `config.py` — `pydantic-settings` reads `.env`. Singleton `settings` object imported everywhere.

**SSE event types:** `token`, `tool_start`, `tool_end`, `done`, `error`.

## Configuration

Create `.env` in the project root:

```env
OPENAI_API_KEY=<key>
SPRING_BASE_URL=http://localhost:8080
REDIS_URL=redis://localhost:6379
MODEL_NAME=gpt-4o-mini
REQUEST_TIMEOUT=10.0
```

The Spring Boot backend must be running at `SPRING_BASE_URL` for any tool call to succeed. Redis is optional.

## Design notes

- The React frontend never calls this service directly — Spring Boot is intended to proxy `/chat` requests, adding user context and auth.
- `user_id` in the request body is currently unused by the agent; `session_id` alone drives conversation continuity via the checkpointer `thread_id`.
- Tools cap results at 10 items before formatting to avoid oversized LLM context.
