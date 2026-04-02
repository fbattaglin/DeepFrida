import { useState } from 'react'

import type { Preset } from '../types'
import styles from './PromptLibrary.module.css'

interface PromptLibraryProps {
  presets: Preset[]
  activePrompt: string
  activePromptName: string | null
  activeTurnCount: number
  isApplyingPrompt: boolean
  onSelect: (content: string) => Promise<void>
  onClearActivePrompt: () => void
  onStartFreshWithPrompt: (content: string) => Promise<void>
  onCreate: (name: string, content: string) => Promise<void>
  onDelete: (id: string) => Promise<void>
}

export function PromptLibrary({
  presets,
  activePrompt,
  activePromptName,
  activeTurnCount,
  isApplyingPrompt,
  onSelect,
  onClearActivePrompt,
  onStartFreshWithPrompt,
  onCreate,
  onDelete,
}: PromptLibraryProps) {
  const [name, setName] = useState('')
  const [content, setContent] = useState('')

  async function handleCreate() {
    if (!name.trim() || !content.trim()) return
    await onCreate(name.trim(), content.trim())
    setName('')
    setContent('')
  }

  return (
    <div className={styles.panel}>
      <div className={styles.activeCard}>
        <div className={styles.cardHeader}>
          <div>
            <div className={styles.sectionLabel}>Active prompt</div>
            <div className={styles.scope}>Conversation-scoped</div>
          </div>
          <button
            type="button"
            className={styles.clear}
            onClick={onClearActivePrompt}
            disabled={isApplyingPrompt || !activePrompt}
          >
            Clear
          </button>
        </div>
        {activePromptName ? <div className={styles.promptName}>{activePromptName}</div> : null}
        <div className={styles.preview}>{activePrompt || '(none)'}</div>
        <div className={styles.status}>
          {isApplyingPrompt
            ? 'Saving prompt for this conversation...'
            : activePrompt
              ? 'Applied to next reply'
              : 'No system prompt active'}
        </div>
        {activePrompt && activeTurnCount > 0 ? (
          <div className={styles.warning}>
            This conversation already has {activeTurnCount} stored message
            {activeTurnCount === 1 ? '' : 's'}. Earlier turns still influence future replies.
          </div>
        ) : null}
        {activePrompt ? (
          <button
            type="button"
            className={styles.secondaryAction}
            onClick={() => void onStartFreshWithPrompt(activePrompt)}
            disabled={isApplyingPrompt}
          >
            New chat with this prompt
          </button>
        ) : null}
      </div>

      <div className={styles.list}>
        {presets.map((preset) => (
          <div
            key={preset.id}
            className={`${styles.item} ${activePrompt === preset.content ? styles.active : ''}`}
          >
            <button
              type="button"
              className={styles.select}
              onClick={() => void onSelect(preset.content)}
              disabled={isApplyingPrompt}
            >
              <div className={styles.name}>{preset.name}</div>
              <div className={styles.preview}>{preset.content}</div>
            </button>
            <div className={styles.actions}>
              <button
                type="button"
                className={styles.secondaryInline}
                onClick={() => void onStartFreshWithPrompt(preset.content)}
                disabled={isApplyingPrompt}
              >
                New chat
              </button>
              <button type="button" className={styles.delete} onClick={() => void onDelete(preset.id)}>
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className={styles.form}>
        <input
          className={styles.input}
          placeholder="Preset name"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <textarea
          className={styles.textarea}
          placeholder="Preset content"
          value={content}
          onChange={(event) => setContent(event.target.value)}
        />
        <button type="button" className={styles.add} onClick={() => void handleCreate()}>
          + Add preset
        </button>
      </div>
    </div>
  )
}
