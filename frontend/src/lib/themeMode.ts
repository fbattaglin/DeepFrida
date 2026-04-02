import { useEffect, useState } from 'react'

export type ThemeMode = 'light' | 'dark'

function parseColor(value: string) {
  const color = value.trim()

  if (color.startsWith('#')) {
    const hex = color.slice(1)
    const normalized =
      hex.length === 3
        ? hex
            .split('')
            .map((char) => char + char)
            .join('')
        : hex

    if (normalized.length !== 6) {
      return null
    }

    const red = Number.parseInt(normalized.slice(0, 2), 16)
    const green = Number.parseInt(normalized.slice(2, 4), 16)
    const blue = Number.parseInt(normalized.slice(4, 6), 16)
    return { red, green, blue }
  }

  const rgbMatch = color.match(/rgba?\(([^)]+)\)/i)
  if (!rgbMatch) {
    return null
  }

  const channels = rgbMatch[1]
    .split(',')
    .slice(0, 3)
    .map((part) => Number.parseFloat(part.trim()))

  if (channels.some((channel) => Number.isNaN(channel))) {
    return null
  }

  return {
    red: channels[0] ?? 255,
    green: channels[1] ?? 255,
    blue: channels[2] ?? 255,
  }
}

function luminanceChannel(value: number) {
  const normalized = value / 255
  return normalized <= 0.03928 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4
}

export function getThemeMode(): ThemeMode {
  if (typeof window === 'undefined') {
    return 'light'
  }

  const background = getComputedStyle(document.documentElement).getPropertyValue('--bg-base')
  const parsed = parseColor(background)

  if (!parsed) {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }

  const brightness =
    0.2126 * luminanceChannel(parsed.red) +
    0.7152 * luminanceChannel(parsed.green) +
    0.0722 * luminanceChannel(parsed.blue)

  return brightness < 0.32 ? 'dark' : 'light'
}

export function useThemeMode() {
  const [themeMode, setThemeMode] = useState<ThemeMode>(() => getThemeMode())

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const observer = new MutationObserver(() => {
      setThemeMode(getThemeMode())
    })

    const handleChange = () => {
      setThemeMode(getThemeMode())
    }

    media.addEventListener('change', handleChange)
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class', 'style', 'data-theme'],
    })

    return () => {
      media.removeEventListener('change', handleChange)
      observer.disconnect()
    }
  }, [])

  return themeMode
}
