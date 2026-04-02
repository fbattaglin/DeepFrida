import { useEffect, useRef, useState } from 'react'

import type { Message } from '../types'
import { VirtualMessageList } from './VirtualMessageList'
import styles from './ChatWindow.module.css'

interface ChatWindowProps {
  title: string
  messages: Message[]
  draftMessage: string
  activeSystemPrompt: string
  isPromptSaving: boolean
  isStreaming: boolean
  thinkDone: boolean
  canSend: boolean
  onDraftChange: (value: string) => void
  onSend: () => Promise<void>
  onTitleChange: (value: string) => Promise<void>
}

export function ChatWindow({
  title,
  messages,
  draftMessage,
  activeSystemPrompt,
  isPromptSaving,
  isStreaming,
  thinkDone,
  canSend,
  onDraftChange,
  onSend,
  onTitleChange,
}: ChatWindowProps) {
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleInput, setTitleInput] = useState(title)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    setTitleInput(title)
  }, [title])

  useEffect(() => {
    const element = textareaRef.current
    if (!element) return
    element.style.height = 'auto'
    element.style.height = `${Math.min(element.scrollHeight, 120)}px`
  }, [draftMessage])

  async function commitTitle() {
    setEditingTitle(false)
    if (titleInput.trim() && titleInput.trim() !== title) {
      await onTitleChange(titleInput.trim())
    } else {
      setTitleInput(title)
    }
  }

  async function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault()
      await onSend()
    }
  }

  return (
    <section className={styles.window}>
      <header className={styles.header}>
        {editingTitle ? (
          <input
            className={styles.titleInput}
            value={titleInput}
            onChange={(event) => setTitleInput(event.target.value)}
            onBlur={() => void commitTitle()}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault()
                void commitTitle()
              }
            }}
            autoFocus
          />
        ) : (
          <button type="button" className={styles.titleButton} onDoubleClick={() => setEditingTitle(true)}>
            {title}
          </button>
        )}
        <div className={styles.actions}>
          <button type="button" className={styles.ghostButton}>
            Branch
          </button>
          <button type="button" className={styles.ghostButton}>
            Export
          </button>
        </div>
      </header>

      <VirtualMessageList
        className={styles.messages}
        messages={messages}
        isStreaming={isStreaming}
        thinkDone={thinkDone}
      />

      <footer className={styles.inputBar}>
        <div className={styles.promptStrip}>
          <span className={styles.promptLabel}>Conversation prompt</span>
          <span className={styles.promptPreview}>{activeSystemPrompt || '(none)'}</span>
          <span className={`${styles.promptStatus} ${isPromptSaving ? styles.promptSaving : styles.promptReady}`}>
            {isPromptSaving ? 'Saving...' : activeSystemPrompt ? 'Active' : 'Inactive'}
          </span>
        </div>
        <div className={styles.composerRow}>
          <textarea
            ref={textareaRef}
            className={styles.textarea}
            placeholder={canSend ? 'Message DeepFrida…' : 'Select or create a conversation…'}
            value={draftMessage}
            onChange={(event) => onDraftChange(event.target.value)}
            onKeyDown={(event) => void handleKeyDown(event)}
            rows={1}
            disabled={!canSend}
          />
          <button
            type="button"
            className={styles.sendButton}
            disabled={isStreaming || !canSend}
            onClick={() => void onSend()}
            aria-label="Send message"
          >
            <svg viewBox="0 0 24 24" className={styles.sendIcon}>
              <path d="M4 11.5 20 4l-5.5 16-2.8-6.2L4 11.5Z" />
            </svg>
          </button>
        </div>
      </footer>
    </section>
  )
}
