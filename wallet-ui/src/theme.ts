import { createContext, useContext } from 'react'

export type Theme = 'dark' | 'light'

export function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem('theme')   // a display preference, not a secret
    if (saved === 'light' || saved === 'dark') return saved
  } catch { /* storage unavailable: fall through */ }
  return 'dark'
}

export const ThemeCtx = createContext<{ theme: Theme; toggle: () => void }>({
  theme: 'dark',
  toggle: () => {},
})
export const useTheme = () => useContext(ThemeCtx)