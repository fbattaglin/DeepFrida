import { memo, useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react'

import type { Message } from '../types'
import { MessageBubble } from './MessageBubble'
import styles from './VirtualMessageList.module.css'

interface VirtualMessageListProps {
  className?: string
  messages: Message[]
  isStreaming: boolean
  thinkDone: boolean
}

interface LayoutItem {
  key: string
  index: number
  message: Message
  start: number
  end: number
  height: number
}

const OVERSCAN_PX = 640
const VIRTUALIZATION_THRESHOLD = 40

function messageKey(message: Message, index: number) {
  return message.id || `${message.role}-${index}`
}

function estimateMessageHeight(message: Message) {
  const base = message.role === 'user' ? 96 : 156
  const contentSize = message.content.length + message.think_content.length
  return Math.min(720, base + Math.ceil(contentSize / 10))
}

export const VirtualMessageList = memo(function VirtualMessageList({
  className,
  messages,
  isStreaming,
  thinkDone,
}: VirtualMessageListProps) {
  const viewportRef = useRef<HTMLDivElement>(null)
  const measuredHeightsRef = useRef<Map<string, number>>(new Map())
  const stickToBottomRef = useRef(true)
  const [scrollTop, setScrollTop] = useState(0)
  const [viewportHeight, setViewportHeight] = useState(0)
  const [measurementVersion, setMeasurementVersion] = useState(0)

  const layout = useMemo(() => {
    let offset = 0
    const items: LayoutItem[] = messages.map((message, index) => {
      const key = messageKey(message, index)
      const height = measuredHeightsRef.current.get(key) ?? estimateMessageHeight(message)
      const item = {
        key,
        index,
        message,
        start: offset,
        end: offset + height,
        height,
      }
      offset += height
      return item
    })

    return {
      items,
      totalHeight: offset,
    }
  }, [measurementVersion, messages])

  const virtualizationEnabled = messages.length > VIRTUALIZATION_THRESHOLD && viewportHeight > 0

  const visibleItems = useMemo(() => {
    if (!virtualizationEnabled) {
      return layout.items
    }

    const startBoundary = Math.max(0, scrollTop - OVERSCAN_PX)
    const endBoundary = scrollTop + viewportHeight + OVERSCAN_PX

    return layout.items.filter((item) => item.end >= startBoundary && item.start <= endBoundary)
  }, [layout.items, scrollTop, viewportHeight, virtualizationEnabled])

  const topSpacerHeight = virtualizationEnabled && visibleItems.length > 0 ? visibleItems[0].start : 0
  const bottomSpacerHeight =
    virtualizationEnabled && visibleItems.length > 0
      ? Math.max(0, layout.totalHeight - visibleItems[visibleItems.length - 1].end)
      : 0

  const handleScroll = useCallback((event: React.UIEvent<HTMLDivElement>) => {
    const nextScrollTop = event.currentTarget.scrollTop
    const distanceFromBottom =
      event.currentTarget.scrollHeight - nextScrollTop - event.currentTarget.clientHeight

    stickToBottomRef.current = distanceFromBottom < 120
    setScrollTop(nextScrollTop)
  }, [])

  const measureRow = useCallback((key: string, node: HTMLDivElement | null) => {
    if (!node) {
      return
    }

    const nextHeight = Math.ceil(node.getBoundingClientRect().height)
    const previousHeight = measuredHeightsRef.current.get(key)

    if (previousHeight !== nextHeight) {
      measuredHeightsRef.current.set(key, nextHeight)
      setMeasurementVersion((current) => current + 1)
    }
  }, [])

  useLayoutEffect(() => {
    const element = viewportRef.current
    if (!element) {
      return
    }

    const updateViewportHeight = () => {
      setViewportHeight(element.clientHeight)
    }

    updateViewportHeight()
    const resizeObserver = new ResizeObserver(updateViewportHeight)
    resizeObserver.observe(element)

    return () => {
      resizeObserver.disconnect()
    }
  }, [])

  useLayoutEffect(() => {
    const element = viewportRef.current
    if (!element || !stickToBottomRef.current) {
      return
    }

    element.scrollTop = element.scrollHeight
    setScrollTop(element.scrollTop)
  }, [layout.totalHeight, messages])

  return (
    <div
      ref={viewportRef}
      className={`${styles.viewport} ${className ?? ''}`}
      onScroll={handleScroll}
    >
      {topSpacerHeight > 0 ? <div style={{ height: topSpacerHeight }} /> : null}

      {visibleItems.map((item) => (
        <div
          key={item.key}
          ref={(node) => {
            measureRow(item.key, node)
          }}
          className={styles.row}
        >
          <MessageBubble
            message={item.message}
            isStreaming={isStreaming && item.index === messages.length - 1 && item.message.role === 'assistant'}
            thinkDone={thinkDone}
          />
        </div>
      ))}

      {bottomSpacerHeight > 0 ? <div style={{ height: bottomSpacerHeight }} /> : null}
    </div>
  )
})
