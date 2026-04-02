import { lazy, Suspense, useMemo } from 'react'
import type { Components } from 'react-markdown'
import ReactMarkdown from 'react-markdown'
import rehypeKatex from 'rehype-katex'
import remarkMath from 'remark-math'

import { useThemeMode } from '../../lib/themeMode'
import { MarkdownErrorBoundary } from './MarkdownErrorBoundary'

const LazyCodeBlock = lazy(async () => {
  const module = await import('./CodeBlock')
  return { default: module.CodeBlock }
})

const LazyMermaidRenderer = lazy(async () => {
  const module = await import('./MermaidRenderer')
  return { default: module.MermaidRenderer }
})

interface MarkdownRendererProps {
  content: string
}

function mermaidFallback() {
  return 'Unable to render Mermaid diagram.'
}

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  const themeMode = useThemeMode()

  const components = useMemo<Components>(
    () => ({
      code({ className, children, ...props }) {
        const language = className?.replace(/^language-/, '').toLowerCase() ?? ''
        const code = String(children).replace(/\n$/, '')

        if (!language) {
          return (
            <code {...props}>
              {children}
            </code>
          )
        }

        if (language === 'mermaid') {
          return (
            <MarkdownErrorBoundary
              resetKey={code}
              fallback={<div>{mermaidFallback()}</div>}
            >
              <Suspense fallback={<div>Loading Mermaid renderer...</div>}>
                <LazyMermaidRenderer code={code} themeMode={themeMode} />
              </Suspense>
            </MarkdownErrorBoundary>
          )
        }

        return (
          <Suspense fallback={<pre>Loading code block...</pre>}>
            <LazyCodeBlock code={code} language={language} themeMode={themeMode} />
          </Suspense>
        )
      },
    }),
    [themeMode],
  )

  return (
    <ReactMarkdown
      remarkPlugins={[remarkMath]}
      rehypePlugins={[rehypeKatex]}
      components={components}
    >
      {content}
    </ReactMarkdown>
  )
}
