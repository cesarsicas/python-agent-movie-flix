# Flix AI Agent

A FastAPI service that powers the AI chatbot for the Movie-Flix platform. It exposes a single streaming endpoint that runs a [LangGraph](https://github.com/langchain-ai/langgraph) ReAct agent — named **Flix** — backed by GPT-4o-mini and five tools that query the Spring Boot backend in real time.

Responses are streamed token-by-token to the client via **Server-Sent Events (SSE)**, so the UI can render the answer word by word as it arrives.

---

## Architecture

```
React frontend
      │  POST /default/chat  (JWT auth)
      ▼
Spring Boot backend          ← proxies the request, adds user context
      │  POST /chat
      ▼
FastAPI agent service  (this service)
      │
      ├── LangGraph ReAct agent (GPT-4o-mini)
      │       └── decides which tools to call
      │
      ├── tools.py  ← 5 async tools calling Spring Boot
      │
      └── memory.py ← Redis checkpointer (falls back to in-memory)
```

The React frontend never calls this service directly — Spring Boot acts as an authenticated proxy, forwarding the user's message and session context.

---

## Features

- Streaming responses via SSE (token by token)
- Conversation memory per user session (Redis-backed, falls back to in-memory)
- ReAct agent: reasons step-by-step before answering, calls tools as needed
- 5 tools covering search, details, reviews, releases, and live stream info
- Graceful error handling: tool failures are reported naturally without crashing the stream

---

## Requirements

- Python 3.11+
- An [OpenAI API key](https://platform.openai.com/api-keys)
- The Spring Boot backend running at `http://localhost:8080`
- Redis (optional — session memory falls back to in-memory if unavailable)

---

## Setup

```bash
# 1. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment variables
cp .env.example .env   # then fill in your values
```

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=your-openai-api-key
SPRING_BASE_URL=http://localhost:8080
REDIS_URL=redis://localhost:6379
MODEL_NAME=gpt-4o-mini
REQUEST_TIMEOUT=10.0
```

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | Yes | — | OpenAI API key |
| `SPRING_BASE_URL` | No | `http://localhost:8080` | Spring Boot backend URL |
| `REDIS_URL` | No | `redis://localhost:6379` | Redis connection string for session memory |
| `MODEL_NAME` | No | `gpt-4o-mini` | OpenAI model to use |
| `REQUEST_TIMEOUT` | No | `10.0` | Timeout in seconds for tool HTTP calls |

---

## Running

```bash
# Using the start script (recommended)
./start.sh

# Or manually
source venv/bin/activate
uvicorn app:app --reload --port 8081
```

The service starts on **port 8081** by default.

---

## API

### `POST /chat`

Streams the agent's response for a given user message.

**Request body:**
```json
{
  "user_id": "123",
  "session_id": "123",
  "message": "recommend dark sci-fi movies"
}
```

| Field | Description |
|---|---|
| `user_id` | Identifies the user |
| `session_id` | Used as the conversation thread key — same session = shared memory |
| `message` | The user's message |

**Response:** `text/event-stream` — a sequence of SSE events:

| Event | Data | Description |
|---|---|---|
| `token` | `{"content": "..."}` | A streamed chunk of the assistant's reply |
| `tool_start` | `{"tool": "search_titles"}` | The agent started calling a tool |
| `tool_end` | `{"tool": "search_titles"}` | A tool call completed |
| `done` | `{"status": "complete"}` | The full response is complete |
| `error` | `{"message": "..."}` | An unrecoverable error occurred |

**Example stream:**
```
data:{"tool": "search_titles"}
event:tool_start

data:{"tool": "search_titles"}
event:tool_end

data:{"content": "Here are some dark sci-fi picks:"}
event:token

data:{"content": " ..."}
event:token

data:{"status": "complete"}
event:done
```

---

## Tools

The agent has access to five tools, all of which make async HTTP calls to the Spring Boot backend:

| Tool | Spring endpoint | Description |
|---|---|---|
| `search_titles` | `GET /titles/search?query=` | Search movies and TV shows by title, genre, mood, or theme |
| `get_title_details` | `GET /titles/{id}` | Full details: synopsis, runtime, rating, genres |
| `get_title_reviews` | `GET /titles/{id}/reviews` | User reviews for a specific title |
| `get_releases` | `GET /titles/releases` | Latest releases available on the platform |
| `get_current_transmission` | `GET /transmissions/current` | What's currently playing live |

---

## Memory

Conversation history is stored per `session_id`:

- **Redis available:** uses `AsyncRedisSaver` from `langgraph-checkpoint-redis` — memory persists across restarts
- **Redis unavailable:** falls back to `InMemorySaver` — memory is lost on restart

The Spring backend uses the authenticated user's ID as both `user_id` and `session_id`, so each user has one persistent conversation thread.
