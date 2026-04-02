import { useState } from 'react'

import type { Preset } from '../types'
import styles from './PromptLibrary.module.css'

interface PromptLibraryProps {
  presets: Preset[]
  activePrompt: string
  onSelect: (content: string) => void
  onCreate: (name: string, content: string) => Promise<void>
  onDelete: (id: string) => Promise<void>
}

export function PromptLibrary({
  presets,
  activePrompt,
  onSelect,
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
        <div className={styles.sectionLabel}>Active prompt</div>
        <div className={styles.preview}>{activePrompt || '(none)'}</div>
      </div>

      <div className={styles.list}>
        {presets.map((preset) => (
          <div
            key={preset.id}
            className={`${styles.item} ${activePrompt === preset.content ? styles.active : ''}`}
          >
            <button type="button" className={styles.select} onClick={() => onSelect(preset.content)}>
              <div className={styles.name}>{preset.name}</div>
              <div className={styles.preview}>{preset.content}</div>
            </button>
            <button type="button" className={styles.delete} onClick={() => void onDelete(preset.id)}>
              Delete
            </button>
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
