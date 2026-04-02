import { memo, useEffect, useRef } from 'react'

import styles from './ThinkBlock.module.css'

interface ThinkBlockProps {
  content: string
  tokenCount: number
  isStreaming: boolean
}

export const ThinkBlock = memo(function ThinkBlock({ content, tokenCount, isStreaming }: ThinkBlockProps) {
  const contentRef = useRef<HTMLDivElement>(null)

  if (!content.trim() && !isStreaming) {
    return null
  }

  useEffect(() => {
    if (!contentRef.current) return
    contentRef.current.scrollTop = contentRef.current.scrollHeight
  }, [content])

  return (
    <div className={`${styles.block} ${isStreaming ? styles.streamingBlock : styles.doneBlock}`}>
      <div className={styles.header}>
        <span className={`${styles.pulse} ${isStreaming ? styles.streaming : ''}`} />
        <span className={styles.label}>
          {isStreaming ? (
            <>
              Frida is thinking
              <span className={styles.ellipsis}>...</span>
            </>
          ) : (
            `Frida thought for ${tokenCount} tokens`
          )}
        </span>
      </div>
      <div ref={contentRef} className={styles.contentWrap}>
        <pre className={styles.content}>
          {content}
          {isStreaming ? <span className={styles.cursor} /> : null}
        </pre>
      </div>
    </div>
  )
})
