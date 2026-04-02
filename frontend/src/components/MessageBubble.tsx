import { memo, useMemo } from 'react'

import type { Message } from '../types'
import { MarkdownRenderer } from './markdown/MarkdownRenderer'
import { ThinkBlock } from './ThinkBlock'
import styles from './MessageBubble.module.css'

interface MessageBubbleProps {
  message: Message
  isStreaming?: boolean
  thinkDone?: boolean
}

function thinkTokens(content: string) {
  return content.trim() ? content.trim().split(/\s+/).length : 0
}

export const MessageBubble = memo(function MessageBubble({
  message,
  isStreaming = false,
  thinkDone = false,
}: MessageBubbleProps) {
  const renderedMarkdown = useMemo(
    () => <MarkdownRenderer content={message.content} />,
    [message.content],
  )

  if (message.role === 'user') {
    return (
      <div className={styles.userRow}>
        <div className={styles.userBubble}>{message.content}</div>
      </div>
    )
  }

  return (
    <div className={styles.assistantRow}>
      <div className={styles.assistantWrap}>
        {message.think_content.length > 0 ? (
          <ThinkBlock
            content={message.think_content}
            tokenCount={thinkTokens(message.think_content)}
            isStreaming={isStreaming && !thinkDone}
          />
        ) : null}

        {message.think_content.length > 0 && message.content.length > 0 && (thinkDone || !isStreaming) ? (
          <div className={styles.divider} />
        ) : null}

        {message.content.length > 0 ? (
          <div className={`${styles.assistantBubble} ${styles.bubble}`}>
            <div className={styles.answer}>
              {isStreaming ? (
                <span className={styles.streamingText}>
                  {message.content}
                  {thinkDone ? <span className={styles.cursor} /> : null}
                </span>
              ) : (
                renderedMarkdown
              )}
            </div>
          </div>
        ) : null}
        {!isStreaming && (message.tok_per_sec || message.ttft_ms || message.total_tokens) ? (
          <div className={styles.metrics}>
            {message.tok_per_sec ? `${message.tok_per_sec.toFixed(1)} tok/s` : 'tok/s n/a'}
            {' · '}
            {message.ttft_ms ? `${Math.round(message.ttft_ms)} ms TTFT` : 'TTFT n/a'}
            {' · '}
            {thinkTokens(message.think_content)} think tok
          </div>
        ) : null}
      </div>
    </div>
  )
})
