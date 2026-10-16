import { createContext, useContext } from 'react'
import type { Account, SessionResult } from './lib/types'

export type Screen =
  | 'loading' | 'offline' | 'welcome' | 'create' | 'srp' | 'quiz' | 'import' | 'lock' | 'home' | 'security'

export interface Store {
  screen: Screen
  go: (s: Screen) => void
  accounts: Account[]
  selected: string | null
  select: (address: string) => void
  phrase: string | null
  clearPhrase: () => void
  startSession: (r: SessionResult, next: Screen) => void
  refreshAccounts: () => Promise<void>
  lockNow: () => Promise<void>
  retryBoot: () => void
  autolock: number
  idleLeft: () => number          // seconds until auto-lock
}

export const Ctx = createContext<Store | null>(null)

export function useStore(): Store {
  const s = useContext(Ctx)
  if (!s) throw new Error('useStore outside StoreProvider')
  return s
}