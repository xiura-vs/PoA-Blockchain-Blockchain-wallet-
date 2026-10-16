import { useCallback, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { api, session } from './lib/api'
import type { Account, SessionResult } from './lib/types'
import { Ctx } from './store'
import type { Screen, Store } from './store'

export function StoreProvider({ children }: { children: ReactNode }) {
  const [screen, setScreen] = useState<Screen>('loading')
  const [accounts, setAccounts] = useState<Account[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [phrase, setPhrase] = useState<string | null>(null)
  const [autolock, setAutolock] = useState(300)
  const lastRef = useRef(0)                   // last real user activity (set on mount, below)

  // Drop everything secret from memory and show the lock screen.
  const lockLocal = useCallback(() => {
    session.set(null)
    setAccounts([])
    setSelected(null)
    setPhrase(null)
    setScreen('lock')
  }, [])

  // The initial screen state is already 'loading', so nothing is set before the first await.
  const boot = useCallback(async () => {
    try {
      const st = await api.state()
      setAutolock(st.autolock_seconds)
      if (!st.has_vault) {
        session.set(null)
        setScreen('welcome')
      } else if (st.unlocked && session.token) {
        const r = await api.accounts()
        lastRef.current = Date.now()
        setAccounts(r.accounts)
        setSelected(r.accounts[0]?.address ?? null)
        setScreen('home')
      } else {
        session.set(null)
        setScreen('lock')
      }
    } catch {
      setScreen('offline')
    }
  }, [])

  useEffect(() => { lastRef.current = Date.now() }, [])

  // boot() only sets state after awaiting the service, so this is not a synchronous setState
  // oxlint-disable-next-line react/set-state-in-effect
  useEffect(() => { void boot() }, [boot])

  // Any "wallet is locked" answer from the service sends us to the lock screen.
  useEffect(() => { session.onLocked(lockLocal) }, [lockLocal])

  // Auto-lock: real user activity resets the timer (and pings the service, throttled).
  // Background polling never touches it, so an unattended wallet still locks.
  useEffect(() => {
    let lastPing = 0
    const touch = () => {
      const now = Date.now()
      lastRef.current = now
      if (session.token && now - lastPing > 10_000) {
        lastPing = now
        api.ping().catch(() => {})
      }
    }
    window.addEventListener('click', touch)
    window.addEventListener('keydown', touch)
    const timer = setInterval(() => {
      if (session.token && Date.now() - lastRef.current > autolock * 1000) lockLocal()
    }, 1000)
    return () => {
      window.removeEventListener('click', touch)
      window.removeEventListener('keydown', touch)
      clearInterval(timer)
    }
  }, [autolock, lockLocal])

  const startSession = useCallback((r: SessionResult, next: Screen) => {
    session.set(r.token)
    lastRef.current = Date.now()
    setAccounts(r.accounts)
    setSelected(r.accounts[0]?.address ?? null)
    setPhrase(r.mnemonic ?? null)
    setScreen(next)
  }, [])

  const refreshAccounts = useCallback(async () => {
    try {
      const r = await api.accounts()
      setAccounts(r.accounts)
      setSelected((cur) =>
        r.accounts.some((a) => a.address === cur) ? cur : (r.accounts[0]?.address ?? null))
    } catch { /* locked handler or offline: nothing to do here */ }
  }, [])

  const lockNow = useCallback(async () => {
    try { await api.lock() } catch { /* lock locally regardless */ }
    lockLocal()
  }, [lockLocal])

  const idleLeft = useCallback(
    () => Math.max(0, autolock - Math.floor((Date.now() - lastRef.current) / 1000)),
    [autolock],
  )

  const value: Store = {
    screen, go: setScreen, accounts, selected, select: setSelected, phrase,
    clearPhrase: () => setPhrase(null),
    startSession, refreshAccounts, lockNow,
    retryBoot: () => { setScreen('loading'); void boot() },
    autolock, idleLeft,
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}