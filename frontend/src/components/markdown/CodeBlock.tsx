import { useMemo, useState } from 'react'
import { Check, Copy, Play } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import {
  oneDark,
  oneLight,
} from 'react-syntax-highlighter/dist/esm/styles/prism'

import { executePython } from '../../lib/pyodideLoader'
import type { ThemeMode } from '../../lib/themeMode'
import styles from './CodeBlock.module.css'

interface CodeBlockProps {
  code: string
  language: string
  themeMode: ThemeMode
}

type RunStatus = 'idle' | 'loading' | 'running' | 'ready' | 'error'

interface ExecutionState {
  status: RunStatus
  stdout: string
  stderr: string
  error: string
}

const INITIAL_EXECUTION: ExecutionState = {
  status: 'idle',
  stdout: '',
  stderr: '',
  error: '',
}

function normalizeLanguage(language: string) {
  return language.toLowerCase().trim() || 'text'
}

export function CodeBlock({ code, language, themeMode }: CodeBlockProps) {
  const [copied, setCopied] = useState(false)
  const [execution, setExecution] = useState<ExecutionState>(INITIAL_EXECUTION)
  const normalizedLanguage = normalizeLanguage(language)
  const canRun = normalizedLanguage === 'python'

  const highlighterStyle = useMemo(() => (themeMode === 'dark' ? oneDark : oneLight), [themeMode])

  async function handleCopy() {
    await navigator.clipboard.writeText(code)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1600)
  }

  async function handleRun() {
    if (!canRun) {
      return
    }

    setExecution((previous) => ({
      ...previous,
      status: previous.status === 'idle' ? 'loading' : 'running',
      error: '',
      stderr: '',
      stdout: '',
    }))

    try {
      const result = await executePython(code)
      setExecution({
        status: result.error ? 'error' : 'ready',
        stdout: result.stdout,
        stderr: result.stderr,
        error: result.error,
      })
    } catch (error) {
      setExecution({
        status: 'error',
        stdout: '',
        stderr: '',
        error: error instanceof Error ? error.message : 'Unable to execute Python in the browser',
      })
    }
  }

  const runLabel =
    execution.status === 'loading'
      ? 'Loading Pyodide...'
      : execution.status === 'running'
        ? 'Running...'
        : 'Run Code'

  return (
    <div className={styles.shell}>
      <div className={styles.header}>
        <span className={styles.language}>{normalizedLanguage}</span>
        <div className={styles.actions}>
          <button type="button" className={styles.actionButton} onClick={() => void handleCopy()}>
            {copied ? <Check className={styles.icon} /> : <Copy className={styles.icon} />}
            {copied ? 'Copied' : 'Copy'}
          </button>
          {canRun ? (
            <button
              type="button"
              className={styles.actionButton}
              onClick={() => void handleRun()}
              disabled={execution.status === 'loading' || execution.status === 'running'}
            >
              <Play className={styles.icon} />
              {runLabel}
            </button>
          ) : null}
        </div>
      </div>

      <div className={styles.codeSurface}>
        <SyntaxHighlighter
          language={normalizedLanguage}
          style={highlighterStyle}
          customStyle={{
            margin: 0,
            padding: '16px 18px',
            background: 'transparent',
          }}
          codeTagProps={{
            style: {
              fontFamily: '"SF Mono", "Menlo", monospace',
            },
          }}
          wrapLongLines
        >
          {code}
        </SyntaxHighlighter>
      </div>

      {canRun && execution.status !== 'idle' ? (
        <div className={styles.output}>
          <div className={styles.outputHeader}>Output</div>
          {execution.status === 'loading' || execution.status === 'running' ? (
            <div className={styles.status}>
              <span className={styles.pulse} />
              {execution.status === 'loading' ? 'Initializing Python sandbox...' : 'Executing code...'}
            </div>
          ) : null}
          {execution.status === 'ready' ? (
            execution.stdout || execution.stderr ? (
              <>
                {execution.stdout ? <pre className={styles.outputBody}>{execution.stdout}</pre> : null}
                {execution.stderr ? <pre className={styles.errorBody}>{execution.stderr}</pre> : null}
              </>
            ) : (
              <div className={styles.emptyOutput}>No output.</div>
            )
          ) : null}
          {execution.status === 'error' ? (
            <>
              {execution.stdout ? <pre className={styles.outputBody}>{execution.stdout}</pre> : null}
              <pre className={styles.errorBody}>{execution.error || execution.stderr}</pre>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
