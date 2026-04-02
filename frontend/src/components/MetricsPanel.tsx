import type { MetricsData } from '../types'
import styles from './MetricsPanel.module.css'

interface MetricsPanelProps {
  metrics: MetricsData
  isGenerating: boolean
}

function toneForRam(value: number) {
  if (value > 22) return styles.bad
  if (value >= 18) return styles.warn
  return styles.good
}

function toneForTps(value: number | null) {
  if (value === null) return ''
  if (value < 15) return styles.bad
  if (value <= 30) return styles.warn
  return styles.good
}

export function MetricsPanel({ metrics, isGenerating }: MetricsPanelProps) {
  const ramClass = toneForRam(metrics.ram_used_gb)
  const tpsClass = toneForTps(metrics.tok_per_sec)
  const memoryPct = Math.min((metrics.ram_used_gb / metrics.ram_total_gb) * 100, 100)

  return (
    <div className={styles.panel}>
      <div className={styles.grid}>
        <div className={styles.card}>
          <div className={`${styles.value} ${ramClass}`}>{metrics.ram_used_gb.toFixed(1)} GB</div>
          <div className={styles.label}>RAM Used</div>
        </div>
        <div className={styles.card}>
          <div className={`${styles.value} ${tpsClass}`}>
            {metrics.tok_per_sec ? metrics.tok_per_sec.toFixed(1) : '—'}
          </div>
          <div className={styles.label}>tok/s</div>
        </div>
        <div className={styles.card}>
          <div className={styles.value}>
            {metrics.ttft_ms ? `${Math.round(metrics.ttft_ms)} ms` : '—'}
          </div>
          <div className={styles.label}>TTFT</div>
        </div>
        <div className={styles.card}>
          <div className={`${styles.value} ${metrics.model_loaded ? styles.good : styles.bad}`}>
            {metrics.model_loaded ? 'Loaded' : 'Idle'}
          </div>
          <div className={styles.label}>{isGenerating ? 'Generating' : 'Model state'}</div>
        </div>
      </div>
      <div className={styles.memoryRow}>
        <div className={styles.memoryMeta}>
          <span>Memory</span>
          <span>
            {metrics.ram_used_gb.toFixed(1)} / {metrics.ram_total_gb} GB
          </span>
        </div>
        <div className={styles.bar}>
          <div className={`${styles.fill} ${ramClass}`} style={{ width: `${memoryPct}%` }} />
        </div>
      </div>
    </div>
  )
}
