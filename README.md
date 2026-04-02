# DeepFrida

DeepFrida is a self-contained local LLM chat application for Ollama, built for a Mac Mini M4 Pro with 24 GB unified memory. It combines a FastAPI backend with a React + Vite + TypeScript frontend, stores application state in SQLite, and streams model output live with separate handling for reasoning blocks.

## Features

- multi-conversation chat UI
- Ollama model listing and loaded-model visibility
- model warmup endpoint
- streaming chat over SSE
- separate `<think>...</think>` reasoning display and storage
- SQLite persistence for conversations, messages, and prompt presets
- live metrics panel for RAM, TTFT, tok/s, and loaded-model state
- DeepFrida logo integrated into the main app branding

## Structure

```text
DeepFrida/
  backend/        FastAPI app, DB layer, API routes
  frontend/       Vite React TypeScript UI
  ollama_client/  copied local Ollama helper package
  assets/         source logo and brand assets
  start.sh        launches backend and frontend together
  deepfrida.db    SQLite database created on first run
```

## Setup

Python:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Frontend:

```bash
cd frontend
npm install
```

The `ollama_client` package is copied into this project and used locally. It is not installed from pip and should not reference the original external ai-lab path at runtime.

## Start

Run both services:

```bash
./start.sh
```

URLs:

- Frontend: [http://localhost:5173](http://localhost:5173)
- Backend: [http://localhost:8000](http://localhost:8000)

Run backend only:

```bash
cd backend
../.venv/bin/python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Run frontend only:

```bash
cd frontend
npm run dev
```

## API

Health:

- `GET /api/health`

Conversations:

- `GET /api/conversations`
- `POST /api/conversations`
- `GET /api/conversations/{id}`
- `PATCH /api/conversations/{id}`
- `DELETE /api/conversations/{id}`

Models:

- `GET /api/models`
- `GET /api/models/loaded`
- `POST /api/models/warmup`

Metrics:

- `GET /api/metrics`

Presets:

- `GET /api/presets`
- `POST /api/presets`
- `DELETE /api/presets/{id}`

Chat:

- `POST /api/chat`
- response type: `text/event-stream`

## SSE Protocol

The chat stream emits events like:

```text
data: {"type":"token","content":"..."}
data: {"type":"think","content":"..."}
data: {"type":"metrics","ttft_ms":41.0,"tok_per_sec":38.2}
data: {"type":"done","total_tokens":187}
data: {"type":"error","message":"..."}
```

Streaming behavior:

- user message is saved immediately
- assistant answer tokens stream incrementally
- reasoning inside `<think>...</think>` streams separately as `type="think"`
- final assistant answer is stored without raw think tags
- final message metrics are stored with the assistant message

## Persistence

SQLite file:

```text
deepfrida.db
```

Persisted data:

- conversations
- messages
- presets

No browser localStorage is used for app persistence.

## Notes

- Ollama must be reachable at `http://localhost:11434`
- backend async HTTP calls use `httpx.AsyncClient`
- frontend styling uses CSS modules and inline SVG only
