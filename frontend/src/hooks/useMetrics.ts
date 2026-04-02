import { useEffect, useState } from 'react'

import type { MetricsData } from '../types'

const API_BASE = '/api'

const DEFAULT_METRICS: MetricsData = {
  ram_used_gb: 0,
  ram_total_gb: 24,
  tok_per_sec: null,
  ttft_ms: null,
  model_loaded: false,
}

export function useMetrics(isGenerating: boolean) {
  const [metrics, setMetrics] = useState<MetricsData>(DEFAULT_METRICS)

  useEffect(() => {
    let active = true
    const intervalMs = isGenerating ? 3000 : 10000

    async function loadMetrics() {
      try {
        const response = await fetch(`${API_BASE}/metrics`)
        if (!response.ok) return
        const data = (await response.json()) as MetricsData
        if (active) {
          setMetrics(data)
        }
      } catch {
        if (active) {
          setMetrics((previous) => ({
            ...previous,
            model_loaded: false,
          }))
        }
      }
    }

    void loadMetrics()
    const interval = window.setInterval(() => {
      void loadMetrics()
    }, intervalMs)

    return () => {
      active = false
      window.clearInterval(interval)
    }
  }, [isGenerating])

  return metrics
}
