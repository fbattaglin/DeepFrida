# DeepFrida

DeepFrida is a self-contained local LLM workstation for Ollama, built for a Mac Mini M4 Pro with 24 GB unified memory. It pairs a FastAPI backend with a React 19 + TypeScript frontend, persists application state in SQLite, and streams reasoning and final answers separately so local models can be inspected, steered, and used interactively.

## Core Capabilities

- multi-conversation local chat with persistent history
- conversation-scoped system prompts and reusable prompt presets
- live SSE streaming for both reasoning and final answer content
- Ollama model listing, load visibility, and warmup flow
- inference observability with TTFT, tok/s, RAM, and structured inference logs
- interactive markdown rendering with Mermaid diagrams and LaTeX
- browser-side Python sandbox for markdown code blocks via lazy-loaded Pyodide
- responsive chat UX with virtualized history rendering and real-time think streaming

## Architecture

```text
DeepFrida/
  backend/
    routes/                  FastAPI API surface
    services/                async Ollama client, stream parser, observability
    db.py                    SQLite pool, schema, repositories
  frontend/
    src/components/
      markdown/              markdown, Mermaid, KaTeX, Python sandbox UI
    src/hooks/               stream and metrics hooks
    src/lib/                 frontend runtime helpers
  ollama_client/             copied local helper package
  assets/                    source branding
  start.sh                   starts frontend and backend together
  deepfrida.db               SQLite database
```

## Backend Highlights

- FastAPI + async streaming with `httpx.AsyncClient`
- robust parser for reasoning emitted either as `<think>...</think>` or Ollama `thinking` fields
- SQLite connection pool with WAL mode, `busy_timeout`, and indexes for conversation/message access
- structured inference events including prompt preview, inference options, TTFT, tok/s, and completion status
- `inference_runs` table for operational telemetry

## Frontend Highlights

- React 19 + TypeScript + Vite
- CSS Modules, desktop-first layout, and persistent composer visibility
- prompt UX that shows the active conversation prompt directly above the composer
- warning when a prompt is changed on a conversation that already has history
- `New chat with this prompt` shortcut for starting a fresh conversation with no prior context carryover
- markdown rendering with syntax highlighting, Mermaid, KaTeX, and Python code execution in-browser

## Prompt Behavior

System prompts are stored per conversation. When the prompt changes on a conversation with history, DeepFrida starts a new prompt scope for future generations: earlier turns remain visible in the UI and database, but only messages from the current prompt scope are sent back to the model. If you want an even cleaner boundary, use `New chat with this prompt`.

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

The `ollama_client` package is copied into this project and used locally. Runtime code should not reference the original external ai-lab path.

## Run

Start both services:

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

## API Surface

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

- user messages are persisted immediately
- think content is streamed live token by token before the answer
- answer content streams independently below the think block
- assistant messages are stored as `content` plus `think_content`
- inference metrics are emitted at the end of the stream and persisted for observability

## Persistence

SQLite file:

```text
deepfrida.db
```

Persisted entities:

- conversations
- messages
- presets
- inference runs

SQLite may also create `deepfrida.db-wal` and `deepfrida.db-shm` while the app is running because WAL mode is enabled.

## Developer Notes

- Ollama must be reachable at `http://localhost:11434`
- backend async calls use `httpx.AsyncClient`
- no browser `localStorage` is used for app state persistence
- Python sandbox execution happens in the browser, not in the backend
- archived exploratory lab material lives under `docs/archive/`
