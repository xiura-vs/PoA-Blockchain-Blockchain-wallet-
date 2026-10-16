import { useState } from 'react'
import type { FormEvent } from 'react'
import { motion } from 'framer-motion'
import { Lock as LockIcon } from 'lucide-react'
import { api } from '../lib/api'
import { useStore } from '../store'
import { Button, Input } from '../components/ui'
import { errMsg } from './helpers'

export function Lock() {
  const { startSession } = useStore()
  const [pw, setPw] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      startSession(await api.unlock(pw), 'home')
    } catch (err) {
      setError(errMsg(err))          // includes the "too many wrong passwords, try again in Ns" message
      setBusy(false)
      setPw('')
    }
  }

  return (
    <div className="flex flex-col items-center px-6 pb-8 pt-10">
      <motion.div initial={{ scale: 0.85, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
        className="grid size-20 place-items-center rounded-3xl bg-surface-2">
        <LockIcon className="size-9 text-accent" />
      </motion.div>
      <h1 className="mt-5 text-2xl font-bold tracking-tight">Welcome back</h1>
      <p className="mt-1 text-sm text-dim">Your wallet is locked</p>

      <form onSubmit={submit} className="mt-6 w-full space-y-3">
        <Input label="Password" type="password" autoFocus autoComplete="current-password"
               value={pw} onChange={(e) => setPw(e.target.value)} />
        <div className="min-h-5 text-sm text-bad">{error}</div>
        <Button type="submit" loading={busy}>Unlock</Button>
      </form>

      <p className="mt-8 text-center text-xs text-dim">
        Forgot your password? Stop the service, delete <span className="font-mono">wallet_vault.json</span>,
        restart it, and import your Secret Recovery Phrase.
      </p>
    </div>
  )
}