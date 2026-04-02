# DeepFrida Frontend

This frontend is the interactive workstation for DeepFrida. It is built with React 19, TypeScript, Vite, CSS Modules, and a small set of focused rendering libraries for AI output.

## What It Does

- streams assistant reasoning and final answer separately in real time
- renders markdown responses with headings, lists, code blocks, links, Mermaid diagrams, and LaTeX
- executes Python snippets locally in the browser through a lazy-loaded Pyodide sandbox
- keeps long conversations responsive with incremental stream state updates and a virtualized message list
- exposes model, metrics, prompt presets, and conversation management in a desktop-first layout

## Key Directories

```text
frontend/
  src/
    components/
      markdown/              interactive markdown renderers and code blocks
      VirtualMessageList.tsx virtualized chat list
    hooks/
      useStream.ts           POST + SSE stream handling
      useMetrics.ts          polling for backend metrics
    lib/
      pyodideLoader.ts       lazy browser sandbox loader
      themeMode.ts           theme helpers for renderers
```

## Prompt UX

System prompts are conversation-scoped. Selecting a preset updates the active conversation and applies to the next reply, but earlier turns in that same conversation still remain in context. When strict behavior is required, the UI exposes `New chat with this prompt` to start a fresh conversation with the selected preset and no prior conversation history.

## Development

Install dependencies:

```bash
npm install
```

Run the dev server:

```bash
npm run dev
```

Build for production:

```bash
npm run build
```

## Main Dependencies

- `react-markdown`
- `remark-math`
- `rehype-katex`
- `mermaid`
- `react-syntax-highlighter`
- `lucide-react`

Pyodide is loaded on demand the first time a Python code block is executed, so it does not sit in the main bundle hot path during initial app startup.
