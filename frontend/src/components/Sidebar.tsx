import { memo } from 'react'

import type { Conversation, ModelInfo } from '../types'
import styles from './Sidebar.module.css'

interface SidebarProps {
  conversations: Conversation[]
  activeConversationId: string | null
  models: ModelInfo[]
  loadedModels: string[]
  activeModel: string
  isActiveModelLoaded: boolean
  isWarmingUp: boolean
  deletingConversationId: string | null
  canDeleteConversations: boolean
  onSelectConversation: (id: string) => void
  onNewConversation: () => Promise<void>
  onDeleteConversation: (id: string) => Promise<void>
  onModelChange: (model: string) => Promise<void>
  onWarmupModel: (model?: string) => Promise<boolean>
}

function shortSize(size?: number) {
  if (!size) return 'local'
  return `${(size / 1_000_000_000).toFixed(1)}B`
}

export const Sidebar = memo(function Sidebar({
  conversations,
  activeConversationId,
  models,
  loadedModels,
  activeModel,
  isActiveModelLoaded,
  isWarmingUp,
  deletingConversationId,
  canDeleteConversations,
  onSelectConversation,
  onNewConversation,
  onDeleteConversation,
  onModelChange,
  onWarmupModel,
}: SidebarProps) {
  return (
    <aside className={styles.sidebar}>
      <div className={styles.brand}>
        <img className={styles.logo} src="/logo.png" alt="DeepFrida logo" />
        <div>
          <div className={styles.name}>DeepFrida</div>
          <div className={styles.meta}>M4 Pro · 24 GB</div>
        </div>
      </div>

      <div className={styles.modelCard}>
        <div className={styles.modelLabel}>Active model</div>
        <select
          className={styles.select}
          value={activeModel}
          onChange={(event) => void onModelChange(event.target.value)}
        >
          {models.map((model) => (
            <option key={model.name} value={model.name}>
              {model.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          className={styles.warmupButton}
          onClick={() => void onWarmupModel(activeModel)}
          disabled={isWarmingUp || !activeModel}
        >
          {isWarmingUp ? 'Warming up...' : isActiveModelLoaded ? 'Model loaded' : 'Warm up model'}
        </button>
        <div className={styles.modelList}>
          {models.map((model) => (
            <div key={model.name} className={styles.modelRow}>
              <span>{model.name}</span>
              <span className={styles.badges}>
                <span>{shortSize(model.size)}</span>
                {loadedModels.includes(model.name) ? <span className={styles.loaded}>● loaded</span> : null}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className={styles.conversationArea}>
        <div className={styles.sectionTitle}>Conversations</div>
        <div className={styles.list}>
          {conversations.length === 0 ? <div className={styles.empty}>No saved conversations yet.</div> : null}
          {conversations.map((conversation) => {
            const isDeleting = deletingConversationId === conversation.id
            return (
              <div key={conversation.id} className={styles.itemRow}>
                <button
                  type="button"
                  className={`${styles.item} ${activeConversationId === conversation.id ? styles.active : ''}`}
                  onClick={() => onSelectConversation(conversation.id)}
                >
                  <span className={styles.itemTitle}>{conversation.title}</span>
                  <span className={styles.itemMeta}>
                    {conversation.model} · {conversation.turn_count ?? 0} msgs
                  </span>
                </button>
                <button
                  type="button"
                  className={styles.deleteButton}
                  onClick={() => void onDeleteConversation(conversation.id)}
                  disabled={isDeleting || !canDeleteConversations}
                  aria-label={`Delete conversation ${conversation.title}`}
                  title={isDeleting ? 'Deleting conversation...' : 'Delete conversation'}
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true" className={styles.deleteIcon}>
                    <path d="M9 4.5h6m-9 3h12m-9.5 0v10.2a1 1 0 0 0 1 1h5a1 1 0 0 0 1-1V7.5m-5-3v3m2-3v3" />
                  </svg>
                </button>
              </div>
            )
          })}
        </div>
      </div>

      <button type="button" className={styles.newButton} onClick={() => void onNewConversation()}>
        + New conversation
      </button>
    </aside>
  )
})
