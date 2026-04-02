import type { InferenceParams } from '../types'
import styles from './ParamSliders.module.css'

interface ParamSlidersProps {
  params: InferenceParams
  onChange: (params: InferenceParams) => void
}

const DEFAULTS: InferenceParams = {
  temperature: 0.6,
  top_p: 0.9,
  num_ctx: 4096,
}

export function ParamSliders({ params, onChange }: ParamSlidersProps) {
  return (
    <div className={styles.panel}>
      <label className={styles.row}>
        <span className={styles.label}>Temperature</span>
        <input
          className={styles.slider}
          type="range"
          min="0"
          max="1.5"
          step="0.1"
          value={params.temperature}
          onChange={(event) =>
            onChange({ ...params, temperature: Number(event.target.value) })
          }
        />
        <span className={styles.value}>{params.temperature.toFixed(1)}</span>
      </label>

      <label className={styles.row}>
        <span className={styles.label}>Top P</span>
        <input
          className={styles.slider}
          type="range"
          min="0.1"
          max="1"
          step="0.05"
          value={params.top_p}
          onChange={(event) => onChange({ ...params, top_p: Number(event.target.value) })}
        />
        <span className={styles.value}>{params.top_p.toFixed(2)}</span>
      </label>

      <label className={styles.row}>
        <span className={styles.label}>Context</span>
        <input
          className={styles.slider}
          type="range"
          min="1024"
          max="8192"
          step="512"
          value={params.num_ctx}
          onChange={(event) => onChange({ ...params, num_ctx: Number(event.target.value) })}
        />
        <span className={styles.value}>{params.num_ctx}</span>
      </label>

      <button type="button" className={styles.reset} onClick={() => onChange(DEFAULTS)}>
        Reset to defaults
      </button>
    </div>
  )
}
