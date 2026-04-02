import { useEffect, useId, useState } from 'react'

import type { ThemeMode } from '../../lib/themeMode'
import styles from './MermaidRenderer.module.css'

interface MermaidRendererProps {
  code: string
  themeMode: ThemeMode
}

function mermaidThemeVariables(themeMode: ThemeMode) {
  if (themeMode === 'dark') {
    return {
      background: '#101419',
      primaryColor: '#163362',
      primaryTextColor: '#f4f7fb',
      primaryBorderColor: '#5e8ce8',
      lineColor: '#90a8dc',
      secondaryColor: '#151b25',
      tertiaryColor: '#0f141c',
      textColor: '#f4f7fb',
    }
  }

  return {
    background: '#f8faff',
    primaryColor: '#eaf1ff',
    primaryTextColor: '#1b2430',
    primaryBorderColor: '#2f63d8',
    lineColor: '#5c76ad',
    secondaryColor: '#ffffff',
    tertiaryColor: '#f2f5fb',
    textColor: '#1b2430',
  }
}

export function MermaidRenderer({ code, themeMode }: MermaidRendererProps) {
  const [svg, setSvg] = useState('')
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const elementId = useId().replace(/:/g, '_')

  useEffect(() => {
    let active = true

    async function renderDiagram() {
      setStatus('loading')
      setSvg('')
      setErrorMessage(null)

      try {
        const mermaidModule = await import('mermaid')
        const mermaid = mermaidModule.default

        mermaid.initialize({
          startOnLoad: false,
          securityLevel: 'strict',
          theme: 'base',
          themeVariables: mermaidThemeVariables(themeMode),
        })

        const { svg: nextSvg } = await mermaid.render(`mermaid-${elementId}`, code)
        if (!active) {
          return
        }

        setSvg(nextSvg)
        setStatus('ready')
      } catch (error) {
        if (!active) {
          return
        }

        setStatus('error')
        setErrorMessage(error instanceof Error ? error.message : 'Unable to render Mermaid diagram')
      }
    }

    void renderDiagram()

    return () => {
      active = false
    }
  }, [code, elementId, themeMode])

  if (status === 'error') {
    return <div className={styles.error}>{errorMessage ?? 'Unable to render Mermaid diagram'}</div>
  }

  return (
    <div className={styles.shell}>
      {status === 'loading' ? (
        <div className={styles.status}>
          <span className={styles.dot} />
          Rendering Mermaid diagram...
        </div>
      ) : null}
      {svg ? <div className={styles.diagram} dangerouslySetInnerHTML={{ __html: svg }} /> : null}
    </div>
  )
}
