import { startTransition, useCallback, useEffect, useRef, useState } from 'react'

import type { InferenceParams, SSEEvent } from '../types'

const API_BASE = '/api'
const MAX_CONNECT_RETRIES = 1

interface StreamMetrics {
  ttft_ms: number | null
  tok_per_sec: number | null
  total_tokens: number | null
}

interface StreamState {
  isStreaming: boolean
  currentContent: string
  currentThink: string
  thinkDone: boolean
  metrics: StreamMetrics
}

interface SendMessageArgs {
  conversationId: string
  message: string
  model: string
  systemPrompt: string
  params: InferenceParams
}

const INITIAL_STATE: StreamState = {
  isStreaming: false,
  currentContent: '',
  currentThink: '',
  thinkDone: false,
  metrics: {
    ttft_ms: null,
    tok_per_sec: null,
    total_tokens: null,
  },
}

function cloneState(state: StreamState): StreamState {
  return {
    ...state,
    metrics: {
      ...state.metrics,
    },
  }
}

function parseEventBlock(block: string): SSEEvent | null {
  const payloadLines = block
    .split('\n')
    .filter((line) => line.startsWith('data: '))
    .map((line) => line.slice(6))

  if (payloadLines.length === 0) {
    return null
  }

  return JSON.parse(payloadLines.join('\n')) as SSEEvent
}

function isRetryableStreamError(error: unknown): boolean {
  return error instanceof TypeError
}

function sleep(ms: number) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms)
  })
}

export function useStream() {
  const [state, setState] = useState<StreamState>(INITIAL_STATE)
  const pendingRef = useRef<StreamState>(cloneState(INITIAL_STATE))
  const frameRef = useRef<number | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const flushState = useCallback((immediate = false) => {
    const commit = () => {
      startTransition(() => {
        setState(cloneState(pendingRef.current))
      })
    }

    if (immediate) {
      if (frameRef.current !== null) {
        window.cancelAnimationFrame(frameRef.current)
        frameRef.current = null
      }
      commit()
      return
    }

    if (frameRef.current !== null) {
      return
    }

    frameRef.current = window.requestAnimationFrame(() => {
      frameRef.current = null
      commit()
    })
  }, [])

  const mutatePending = useCallback(
    (mutator: (draft: StreamState) => void, immediate = false) => {
      mutator(pendingRef.current)
      flushState(immediate)
    },
    [flushState],
  )

  const resetStream = useCallback(() => {
    pendingRef.current = cloneState(INITIAL_STATE)
    flushState(true)
  }, [flushState])

  useEffect(() => {
    return () => {
      if (frameRef.current !== null) {
        window.cancelAnimationFrame(frameRef.current)
      }
      abortRef.current?.abort()
    }
  }, [])

  async function streamOnce(args: SendMessageArgs, controller: AbortController) {
    const response = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        conversation_id: args.conversationId,
        message: args.message,
        model: args.model,
        system_prompt: args.systemPrompt,
        options: args.params,
      }),
      signal: controller.signal,
    })

    if (!response.ok || !response.body) {
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
        // Keep the default status-based message when the payload is not JSON.
      }
      throw new Error(message)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let receivedPayload = false

    while (true) {
      const { value, done } = await reader.read()
      if (done) {
        break
      }

      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop() ?? ''

      for (const part of parts) {
        const payload = parseEventBlock(part)
        if (!payload) {
          continue
        }

        receivedPayload = true

        if (payload.type === 'token') {
          mutatePending((draft) => {
            draft.thinkDone = true
            draft.currentContent += payload.content
          })
        } else if (payload.type === 'think') {
          mutatePending((draft) => {
            draft.currentThink += payload.content
          })
        } else if (payload.type === 'metrics') {
          mutatePending((draft) => {
            draft.metrics.ttft_ms = payload.ttft_ms
            draft.metrics.tok_per_sec = payload.tok_per_sec
          })
        } else if (payload.type === 'done') {
          mutatePending(
            (draft) => {
              draft.metrics.total_tokens = payload.total_tokens
            },
            true,
          )
        } else if (payload.type === 'error') {
          throw new Error(payload.message)
        }
      }
    }

    if (buffer.trim()) {
      const payload = parseEventBlock(buffer)
      if (payload?.type === 'token') {
        mutatePending((draft) => {
          draft.thinkDone = true
          draft.currentContent += payload.content
        }, true)
      } else if (payload?.type === 'think') {
        mutatePending((draft) => {
          draft.currentThink += payload.content
        }, true)
      } else if (payload?.type === 'metrics') {
        mutatePending((draft) => {
          draft.metrics.ttft_ms = payload.ttft_ms
          draft.metrics.tok_per_sec = payload.tok_per_sec
        }, true)
      } else if (payload?.type === 'done') {
        mutatePending((draft) => {
          draft.metrics.total_tokens = payload.total_tokens
        }, true)
      } else if (payload?.type === 'error') {
        throw new Error(payload.message)
      }
    }

    return receivedPayload
  }

  async function sendMessage(args: SendMessageArgs) {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    pendingRef.current = cloneState({
      ...INITIAL_STATE,
      isStreaming: true,
    })
    flushState(true)

    let receivedPayload = false

    try {
      for (let attempt = 0; attempt <= MAX_CONNECT_RETRIES; attempt += 1) {
        try {
          receivedPayload = await streamOnce(args, controller)
          break
        } catch (error) {
          if (controller.signal.aborted) {
            throw error
          }

          const shouldRetry =
            attempt < MAX_CONNECT_RETRIES && !receivedPayload && isRetryableStreamError(error)

          if (!shouldRetry) {
            throw error
          }

          await sleep(250 * (attempt + 1))
        }
      }

      return cloneState(pendingRef.current)
    } finally {
      mutatePending((draft) => {
        draft.isStreaming = false
      }, true)
    }
  }

  return {
    isStreaming: state.isStreaming,
    currentContent: state.currentContent,
    currentThink: state.currentThink,
    thinkDone: state.thinkDone,
    metrics: state.metrics,
    sendMessage,
    resetStream,
  }
}
