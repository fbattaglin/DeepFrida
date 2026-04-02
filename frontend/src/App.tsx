import { useEffect, useMemo, useState } from 'react'

import { ChatWindow } from './components/ChatWindow'
import { MetricsPanel } from './components/MetricsPanel'
import { ParamSliders } from './components/ParamSliders'
import { PromptLibrary } from './components/PromptLibrary'
import { Sidebar } from './components/Sidebar'
import { useMetrics } from './hooks/useMetrics'
import { useStream } from './hooks/useStream'
import type { Conversation, InferenceParams, Message, ModelInfo, Preset } from './types'
import styles from './App.module.css'

const API_BASE = '/api'

const DEFAULT_PARAMS: InferenceParams = {
  temperature: 0.6,
  top_p: 0.9,
  num_ctx: 4096,
}

async function readJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  if (!response.ok) {
    let message = `Request failed: ${response.status}`
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
  return (await response.json()) as T
}

function buildStreamingMessage(
  conversationId: string,
  content: string,
  think: string,
  tokPerSec: number | null,
  ttftMs: number | null,
): Message {
  return {
    id: 'streaming-assistant',
    conversation_id: conversationId,
    role: 'assistant',
    content,
    think_content: think,
    created_at: new Date().toISOString(),
    tok_per_sec: tokPerSec,
    ttft_ms: ttftMs,
    total_tokens: null,
  }
}

function machineContext(model: string, models: ModelInfo[]) {
  return models.find((entry) => entry.name === model)?.name ?? model
}

function promptPresetLabel(content: string, presets: Preset[]) {
  if (!content.trim()) return null
  return presets.find((preset) => preset.content === content)?.name ?? 'Custom prompt'
}

interface CreateConversationOptions {
  model?: string
  systemPrompt?: string
  title?: string
}

export default function App() {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)
  const [messagesByConversation, setMessagesByConversation] = useState<Record<string, Message[]>>({})
  const [presets, setPresets] = useState<Preset[]>([])
  const [models, setModels] = useState<ModelInfo[]>([])
  const [loadedModels, setLoadedModels] = useState<string[]>([])
  const [draftMessage, setDraftMessage] = useState('')
  const [params, setParams] = useState<InferenceParams>(DEFAULT_PARAMS)
  const [activeTab, setActiveTab] = useState<'stats' | 'params' | 'prompts'>('stats')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [deletingConversationId, setDeletingConversationId] = useState<string | null>(null)
  const [savingPromptConversationId, setSavingPromptConversationId] = useState<string | null>(null)

  const {
    isStreaming,
    currentContent,
    currentThink,
    thinkDone,
    metrics: streamMetrics,
    sendMessage,
  } = useStream()
  const metrics = useMetrics(isStreaming)

  const activeConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === activeConversationId) ?? null,
    [activeConversationId, conversations],
  )
  const activeSystemPrompt = activeConversation?.system_prompt ?? ''

  const baseMessages = activeConversationId ? messagesByConversation[activeConversationId] ?? [] : []
  const displayMessages = useMemo(() => {
    if (!activeConversationId || !isStreaming) {
      return baseMessages
    }

    return [
      ...baseMessages,
      buildStreamingMessage(
        activeConversationId,
        currentContent,
        currentThink,
        streamMetrics.tok_per_sec,
        streamMetrics.ttft_ms,
      ),
    ]
  }, [
    activeConversationId,
    baseMessages,
    currentContent,
    currentThink,
    isStreaming,
    streamMetrics.tok_per_sec,
    streamMetrics.ttft_ms,
  ])

  async function loadConversations(preferredActiveId?: string | null) {
    const data = await readJson<Conversation[]>(`${API_BASE}/conversations`)
    setConversations(data)
    setActiveConversationId((currentId) => {
      const nextPreferredId = preferredActiveId === undefined ? currentId : preferredActiveId
      if (nextPreferredId && data.some((conversation) => conversation.id === nextPreferredId)) {
        return nextPreferredId
      }
      return data[0]?.id ?? null
    })
    return data
  }

  async function loadConversation(id: string) {
    const data = await readJson<Conversation>(`${API_BASE}/conversations/${id}`)
    setMessagesByConversation((previous) => ({
      ...previous,
      [id]: data.messages ?? [],
    }))
    setConversations((previous) =>
      previous.map((conversation) => (conversation.id === id ? { ...conversation, ...data } : conversation)),
    )
  }

  async function loadModels() {
    let availableModels: ModelInfo[] = []
    try {
      const tags = await readJson<{ models: ModelInfo[] }>(`${API_BASE}/models`)
      availableModels = tags.models ?? []
      setModels(availableModels)
    } catch {
      setModels([])
    }

    try {
      const loaded = await readJson<{ models: { name: string }[] }>(`${API_BASE}/models/loaded`)
      setLoadedModels((loaded.models ?? []).map((entry) => entry.name))
    } catch {
      setLoadedModels([])
    }

    return availableModels
  }

  async function loadPresets() {
    const data = await readJson<Preset[]>(`${API_BASE}/presets`)
    setPresets(data)
    return data
  }

  async function createConversation(options?: CreateConversationOptions) {
    const model = options?.model ?? activeConversation?.model ?? models[0]?.name ?? 'deepseek-r1:14b'
    const systemPrompt = options?.systemPrompt?.trim() ?? ''
    const title = options?.title ?? 'New conversation'
    const created = await readJson<Conversation>(`${API_BASE}/conversations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title,
        model,
        system_prompt: systemPrompt,
      }),
    })
    setConversations((previous) => [created, ...previous])
    setMessagesByConversation((previous) => ({ ...previous, [created.id]: [] }))
    setActiveConversationId(created.id)

    if (systemPrompt) {
      const successMessage = 'Started a new conversation with the selected prompt'
      setNotice(successMessage)
      window.setTimeout(() => setNotice((previous) => (previous === successMessage ? null : previous)), 2400)
    }
  }

  function patchConversationState(conversationId: string, patch: Partial<Conversation>) {
    setConversations((previous) =>
      previous.map((conversation) =>
        conversation.id === conversationId ? { ...conversation, ...patch } : conversation,
      ),
    )
  }

  async function handleWarmupModel(modelOverride?: string) {
    const model = modelOverride ?? activeConversation?.model ?? models[0]?.name
    if (!model) {
      setError('No model available to warm up')
      return false
    }

    setError(null)
    setNotice(`Warming up ${model}...`)
    setBusy(true)

    try {
      await readJson<{ load_time_s: number }>(`${API_BASE}/models/warmup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model }),
      })
      await loadModels()
      setNotice(`${model} is ready`)
      window.setTimeout(() => setNotice((previous) => (previous === `${model} is ready` ? null : previous)), 2500)
      return true
    } catch (warmupError) {
      setError(warmupError instanceof Error ? warmupError.message : 'Model warmup failed')
      setNotice(null)
      return false
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    async function bootstrap() {
      try {
        const [conversationList, modelList] = await Promise.all([
          loadConversations(),
          loadModels(),
          loadPresets(),
        ])
        if (conversationList.length === 0) {
          await createConversation({ model: modelList[0]?.name ?? 'deepseek-r1:14b' })
        }
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : 'Failed to load DeepFrida')
      }
    }

    void bootstrap()
  }, [])

  useEffect(() => {
    if (activeConversationId && !messagesByConversation[activeConversationId]) {
      void loadConversation(activeConversationId)
    }
  }, [activeConversationId, messagesByConversation])

  async function handleSend() {
    if (!draftMessage.trim() || !activeConversationId) return

    const conversationAtSend =
      conversations.find((conversation) => conversation.id === activeConversationId) ?? null

    if (!conversationAtSend) {
      return
    }

    setError(null)
    setNotice(null)
    setBusy(true)

    try {
      if (!loadedModels.includes(conversationAtSend.model)) {
        const warmedUp = await handleWarmupModel(conversationAtSend.model)
        if (!warmedUp) {
          setBusy(false)
          return
        }
        setBusy(true)
      }
    } catch {
      setBusy(false)
      return
    }

    const optimisticUser: Message = {
      id: `optimistic-user-${Date.now()}`,
      conversation_id: conversationAtSend.id,
      role: 'user',
      content: draftMessage.trim(),
      think_content: '',
      created_at: new Date().toISOString(),
    }

    setMessagesByConversation((previous) => ({
      ...previous,
      [conversationAtSend.id]: [...(previous[conversationAtSend.id] ?? []), optimisticUser],
    }))

    const messageToSend = draftMessage.trim()
    setDraftMessage('')

    try {
      await sendMessage({
        conversationId: conversationAtSend.id,
        message: messageToSend,
        model: conversationAtSend.model,
        systemPrompt: conversationAtSend.system_prompt,
        params,
      })
      await Promise.all([loadConversation(conversationAtSend.id), loadConversations(), loadModels()])
    } catch (streamError) {
      setError(streamError instanceof Error ? streamError.message : 'Streaming failed')
      await loadConversation(conversationAtSend.id)
    } finally {
      setBusy(false)
    }
  }

  async function handleTitleChange(value: string) {
    if (!activeConversation) return
    const updated = await readJson<Conversation>(`${API_BASE}/conversations/${activeConversation.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: value }),
    })
    setConversations((previous) =>
      previous.map((conversation) =>
        conversation.id === activeConversation.id ? { ...conversation, ...updated } : conversation,
      ),
    )
  }

  async function handleSystemPromptChange(content: string) {
    if (!activeConversation) return
    const previousPrompt = activeConversation.system_prompt
    const nextPrompt = content.trim()
    const hasExistingMessages = (messagesByConversation[activeConversation.id]?.length ?? 0) > 0

    patchConversationState(activeConversation.id, { system_prompt: nextPrompt })
    setSavingPromptConversationId(activeConversation.id)
    setError(null)

    try {
      const updated = await readJson<Conversation>(`${API_BASE}/conversations/${activeConversation.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ system_prompt: nextPrompt }),
      })
      patchConversationState(activeConversation.id, updated)
      const successMessage = nextPrompt
        ? hasExistingMessages
          ? 'System prompt applied. Earlier turns still remain in context.'
          : 'System prompt applied to this conversation'
        : 'System prompt cleared'
      setNotice(successMessage)
      window.setTimeout(() => setNotice((previous) => (previous === successMessage ? null : previous)), 2200)
    } catch (promptError) {
      patchConversationState(activeConversation.id, { system_prompt: previousPrompt })
      setError(promptError instanceof Error ? promptError.message : 'Failed to update system prompt')
    } finally {
      setSavingPromptConversationId(null)
    }
  }

  async function handleModelChange(model: string) {
    if (!activeConversation) return
    const updated = await readJson<Conversation>(`${API_BASE}/conversations/${activeConversation.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model }),
    })
    setConversations((previous) =>
      previous.map((conversation) =>
        conversation.id === activeConversation.id ? { ...conversation, ...updated } : conversation,
      ),
    )
  }

  async function handleCreatePreset(name: string, content: string) {
    await readJson<Preset>(`${API_BASE}/presets`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, content }),
    })
    await loadPresets()
  }

  async function handleDeletePreset(id: string) {
    const response = await fetch(`${API_BASE}/presets/${id}`, { method: 'DELETE' })
    if (!response.ok) {
      throw new Error(`Failed to delete preset (${response.status})`)
    }
    await loadPresets()
  }

  async function handleDeleteConversation(id: string) {
    const conversation = conversations.find((entry) => entry.id === id)
    if (!conversation) return

    if (isStreaming || busy) {
      setError('Wait for the current generation to finish before deleting a conversation')
      return
    }

    const confirmed = window.confirm(
      `Delete "${conversation.title}"?\n\nThis will permanently remove the conversation and its stored messages.`,
    )
    if (!confirmed) return

    const deletedIndex = conversations.findIndex((entry) => entry.id === id)
    const remaining = conversations.filter((entry) => entry.id !== id)
    const preferredActiveId =
      activeConversationId === id
        ? remaining[deletedIndex]?.id ?? remaining[deletedIndex - 1]?.id ?? remaining[0]?.id ?? null
        : activeConversationId

    setDeletingConversationId(id)
    setError(null)
    setNotice(null)

    try {
      const response = await fetch(`${API_BASE}/conversations/${id}`, { method: 'DELETE' })
      if (!response.ok) {
        let message = `Failed to delete conversation (${response.status})`
        try {
          const data = (await response.json()) as { error?: string; detail?: string }
          if (typeof data.error === 'string') {
            message = data.error
          } else if (typeof data.detail === 'string') {
            message = data.detail
          }
        } catch {
          // Keep the status-based message when the payload is not JSON.
        }
        throw new Error(message)
      }

      setMessagesByConversation((previous) => {
        const next = { ...previous }
        delete next[id]
        return next
      })
      if (activeConversationId === id) {
        setDraftMessage('')
      }

      const refreshed = await loadConversations(preferredActiveId)
      const resolvedActiveId =
        preferredActiveId && refreshed.some((entry) => entry.id === preferredActiveId)
          ? preferredActiveId
          : refreshed[0]?.id ?? null

      if (resolvedActiveId) {
        await loadConversation(resolvedActiveId)
      }

      const successMessage =
        refreshed.length > 0
          ? `Deleted "${conversation.title}"`
          : `Deleted "${conversation.title}". Create a new conversation when you're ready.`
      setNotice(successMessage)
      window.setTimeout(() => setNotice((previous) => (previous === successMessage ? null : previous)), 3000)
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : 'Failed to delete conversation')
    } finally {
      setDeletingConversationId(null)
    }
  }

  return (
    <div className={styles.appShell}>
      <Sidebar
        conversations={conversations}
        activeConversationId={activeConversationId}
        models={models}
        loadedModels={loadedModels}
        activeModel={activeConversation?.model ?? models[0]?.name ?? 'deepseek-r1:14b'}
        isActiveModelLoaded={Boolean(
          activeConversation?.model && loadedModels.includes(activeConversation.model),
        )}
        isWarmingUp={busy && Boolean(notice?.startsWith('Warming up'))}
        deletingConversationId={deletingConversationId}
        canDeleteConversations={!isStreaming && !busy}
        onSelectConversation={setActiveConversationId}
        onNewConversation={createConversation}
        onDeleteConversation={handleDeleteConversation}
        onModelChange={handleModelChange}
        onWarmupModel={handleWarmupModel}
      />

      <main className={styles.mainPane}>
        {error ? <div className={styles.error}>{error}</div> : null}
        {notice ? <div className={styles.notice}>{notice}</div> : null}
        <ChatWindow
          title={activeConversation?.title ?? 'DeepFrida'}
          messages={displayMessages}
          draftMessage={draftMessage}
          activeSystemPrompt={activeSystemPrompt}
          isPromptSaving={savingPromptConversationId === activeConversationId}
          isStreaming={isStreaming || busy}
          thinkDone={thinkDone}
          canSend={Boolean(activeConversation)}
          onDraftChange={setDraftMessage}
          onSend={handleSend}
          onTitleChange={handleTitleChange}
        />
      </main>

      <aside className={styles.rightPane}>
        <div className={styles.tabs}>
          <button
            type="button"
            className={`${styles.tab} ${activeTab === 'stats' ? styles.activeTab : ''}`}
            onClick={() => setActiveTab('stats')}
          >
            Stats
          </button>
          <button
            type="button"
            className={`${styles.tab} ${activeTab === 'params' ? styles.activeTab : ''}`}
            onClick={() => setActiveTab('params')}
          >
            Params
          </button>
          <button
            type="button"
            className={`${styles.tab} ${activeTab === 'prompts' ? styles.activeTab : ''}`}
            onClick={() => setActiveTab('prompts')}
          >
            Prompts
          </button>
        </div>

        <div className={styles.panelBody}>
          {activeTab === 'stats' ? (
            <MetricsPanel metrics={metrics} isGenerating={isStreaming || busy} />
          ) : null}
          {activeTab === 'params' ? (
            <ParamSliders params={params} onChange={setParams} />
          ) : null}
          {activeTab === 'prompts' ? (
            <PromptLibrary
              presets={presets}
              activePrompt={activeSystemPrompt}
              activePromptName={promptPresetLabel(activeSystemPrompt, presets)}
              activeTurnCount={messagesByConversation[activeConversationId ?? '']?.length ?? 0}
              isApplyingPrompt={savingPromptConversationId === activeConversationId}
              onSelect={handleSystemPromptChange}
              onClearActivePrompt={() => void handleSystemPromptChange('')}
              onStartFreshWithPrompt={async (content) =>
                createConversation({
                  model: activeConversation?.model ?? models[0]?.name ?? 'deepseek-r1:14b',
                  systemPrompt: content,
                  title: 'Prompt conversation',
                })
              }
              onCreate={handleCreatePreset}
              onDelete={handleDeletePreset}
            />
          ) : null}
        </div>
        <div className={styles.footerMeta}>
          Active: {machineContext(activeConversation?.model ?? 'No model', models)}
        </div>
      </aside>
    </div>
  )
}
