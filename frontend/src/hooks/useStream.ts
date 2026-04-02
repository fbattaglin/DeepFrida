import { useState } from 'react'

import type { InferenceParams, SSEEvent } from '../types'

const API_BASE = '/api'

interface StreamMetrics {
  ttft_ms: number | null
  tok_per_sec: number | null
  total_tokens: number | null
}

interface SendMessageArgs {
  conversationId: string
  message: string
  model: string
  systemPrompt: string
  params: InferenceParams
}

export function useStream() {
  const [isStreaming, setIsStreaming] = useState(false)
  const [currentContent, setCurrentContent] = useState('')
  const [currentThink, setCurrentThink] = useState('')
  const [thinkDone, setThinkDone] = useState(false)
  const [metrics, setMetrics] = useState<StreamMetrics>({
    ttft_ms: null,
    tok_per_sec: null,
    total_tokens: null,
  })

  async function sendMessage({
    conversationId,
    message,
    model,
    systemPrompt,
    params,
  }: SendMessageArgs) {
    setIsStreaming(true)
    setCurrentContent('')
    setCurrentThink('')
    setThinkDone(false)
    setMetrics({ ttft_ms: null, tok_per_sec: null, total_tokens: null })

    const response = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        conversation_id: conversationId,
        message,
        model,
        system_prompt: systemPrompt,
        options: params,
      }),
    })

    if (!response.ok || !response.body) {
      setIsStreaming(false)
      let message = `Chat request failed with status ${response.status}`
      try {
        const data = (await response.json()) as { error?: string; detail?: string | { error?: string } }
        if (typeof data.error === 'string') {
          message = data.error
        } else if (typeof data.detail === 'string') {
          message = data.detail
        } else if (typeof data.detail === 'object' && typeof data.detail?.error === 'string') {
          message = data.detail.error
        }
      } catch {
        // Ignore JSON parsing failures and keep the default message.
      }
      throw new Error(message)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    try {
      while (true) {
        const { value, done } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop() ?? ''

        for (const part of parts) {
          const line = part
            .split('\n')
            .find((candidate) => candidate.startsWith('data: '))

          if (!line) continue

          const payload = JSON.parse(line.slice(6)) as SSEEvent
          if (payload.type === 'token') {
            setThinkDone(true)
            setCurrentContent((previous) => previous + payload.content)
          } else if (payload.type === 'think') {
            setCurrentThink((previous) => previous + payload.content)
          } else if (payload.type === 'metrics') {
            setMetrics((previous) => ({
              ...previous,
              ttft_ms: payload.ttft_ms,
              tok_per_sec: payload.tok_per_sec,
            }))
          } else if (payload.type === 'done') {
            setMetrics((previous) => ({
              ...previous,
              total_tokens: payload.total_tokens,
            }))
          } else if (payload.type === 'error') {
            throw new Error(payload.message)
          }
        }
      }
    } finally {
      setIsStreaming(false)
    }

    return {
      content: currentContent,
      think: currentThink,
      metrics,
    }
  }

  function resetStream() {
    setCurrentContent('')
    setCurrentThink('')
    setThinkDone(false)
    setMetrics({ ttft_ms: null, tok_per_sec: null, total_tokens: null })
    setIsStreaming(false)
  }

  return {
    isStreaming,
    currentContent,
    currentThink,
    thinkDone,
    metrics,
    sendMessage,
    resetStream,
  }
}
