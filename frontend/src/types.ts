export interface Conversation {
  id: string
  title: string
  model: string
  system_prompt: string
  prompt_revision?: number
  created_at: string
  updated_at: string
  turn_count?: number
  messages?: Message[]
}

export interface Message {
  id: string
  conversation_id: string
  role: 'user' | 'assistant'
  content: string
  think_content: string
  prompt_revision?: number
  created_at: string
  ttft_ms?: number | null
  tok_per_sec?: number | null
  total_tokens?: number | null
}

export interface MetricsData {
  ram_used_gb: number
  ram_total_gb: number
  tok_per_sec: number | null
  ttft_ms: number | null
  model_loaded: boolean
}

export interface ModelInfo {
  name: string
  size?: number
  modified_at?: string
}

export interface InferenceParams {
  temperature: number
  top_p: number
  num_ctx: number
}

export interface Preset {
  id: string
  name: string
  content: string
  created_at?: string
}

export type SSEEvent =
  | { type: 'token'; content: string }
  | { type: 'think'; content: string }
  | { type: 'metrics'; ttft_ms: number; tok_per_sec: number }
  | { type: 'done'; total_tokens: number }
  | { type: 'error'; message: string }
