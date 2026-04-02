const PYODIDE_VERSION = '0.27.5'
const PYODIDE_BASE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`
const PYODIDE_SCRIPT_URL = `${PYODIDE_BASE_URL}pyodide.js`

interface PyodideGlobals {
  set(name: string, value: unknown): void
  delete?(name: string): void
}

interface PyodideRuntime {
  globals: PyodideGlobals
  loadPackagesFromImports?(code: string): Promise<void>
  runPythonAsync(code: string): Promise<unknown>
}

declare global {
  interface Window {
    loadPyodide?: (options: { indexURL: string }) => Promise<PyodideRuntime>
  }
}

let scriptPromise: Promise<void> | null = null
let runtimePromise: Promise<PyodideRuntime> | null = null

function injectScript() {
  if (scriptPromise) {
    return scriptPromise
  }

  scriptPromise = new Promise((resolve, reject) => {
    const existingScript = document.querySelector<HTMLScriptElement>(`script[src="${PYODIDE_SCRIPT_URL}"]`)
    if (existingScript) {
      if (window.loadPyodide) {
        resolve()
        return
      }

      existingScript.addEventListener('load', () => resolve(), { once: true })
      existingScript.addEventListener('error', () => reject(new Error('Failed to load Pyodide')), { once: true })
      return
    }

    const script = document.createElement('script')
    script.src = PYODIDE_SCRIPT_URL
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Failed to load Pyodide'))
    document.head.appendChild(script)
  })

  return scriptPromise
}

export async function getPyodideRuntime() {
  if (runtimePromise) {
    return runtimePromise
  }

  runtimePromise = (async () => {
    await injectScript()

    if (!window.loadPyodide) {
      throw new Error('Pyodide loader is unavailable')
    }

    return await window.loadPyodide({ indexURL: PYODIDE_BASE_URL })
  })()

  return runtimePromise
}

export interface PythonExecutionResult {
  stdout: string
  stderr: string
  error: string
}

export async function executePython(code: string) {
  const runtime = await getPyodideRuntime()

  if (runtime.loadPackagesFromImports) {
    await runtime.loadPackagesFromImports(code)
  }

  runtime.globals.set('_deepfrida_code', code)

  const rawResult = await runtime.runPythonAsync(`
import io
import json
import traceback
from contextlib import redirect_stdout, redirect_stderr

_deepfrida_stdout = io.StringIO()
_deepfrida_stderr = io.StringIO()
_deepfrida_scope = {}

try:
    with redirect_stdout(_deepfrida_stdout), redirect_stderr(_deepfrida_stderr):
        exec(_deepfrida_code, _deepfrida_scope, _deepfrida_scope)
    _deepfrida_payload = {
        "stdout": _deepfrida_stdout.getvalue(),
        "stderr": _deepfrida_stderr.getvalue(),
        "error": ""
    }
except Exception:
    _deepfrida_payload = {
        "stdout": _deepfrida_stdout.getvalue(),
        "stderr": _deepfrida_stderr.getvalue(),
        "error": traceback.format_exc()
    }

json.dumps(_deepfrida_payload)
`)

  runtime.globals.delete?.('_deepfrida_code')

  return JSON.parse(String(rawResult)) as PythonExecutionResult
}
