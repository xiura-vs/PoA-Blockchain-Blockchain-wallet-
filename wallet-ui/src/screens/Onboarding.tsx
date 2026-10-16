import { useState } from 'react'
import type { FormEvent } from 'react'
import { motion } from 'framer-motion'
import { AlertTriangle, Copy, Eye, KeyRound, Lock, Network, ShieldCheck } from 'lucide-react'
import { api } from '../lib/api'
import { useStore } from '../store'
import { Button, Input } from '../components/ui'
import { cn } from '../lib/utils'
import { useToast } from '../components/useToast'
import { Page, PasswordMeter, Textarea } from './shared'
import { errMsg } from './helpers'

/* ---------------- Welcome ---------------- */
export function Welcome() {
  const { go } = useStore()
  const points = [
    { icon: KeyRound, text: 'You own your keys. Nobody can recover them for you.' },
    { icon: Lock, text: 'Your vault is encrypted with your password.' },
    { icon: Network, text: 'Transactions are signed here, then sent to the PoA network.' },
  ]
  return (
    <div className="flex flex-col items-center px-6 pb-8 pt-10 text-center">
      <motion.div
        initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
        className="grid size-24 place-items-center rounded-3xl"
        style={{ background: 'linear-gradient(135deg, var(--accent), #f472b6)' }}
      >
        <ShieldCheck className="size-12 text-white" />
      </motion.div>
      <h1 className="mt-6 text-3xl font-bold tracking-tight">PoA Wallet</h1>
      <p className="mt-2 text-sm text-dim">A self-custody wallet for the Proof-of-Authority chain.</p>

      <ul className="mt-7 w-full space-y-3 text-left">
        {points.map(({ icon: Icon, text }) => (
          <li key={text} className="flex items-start gap-3 text-sm text-dim">
            <Icon className="mt-0.5 size-4 shrink-0 text-accent" />{text}
          </li>
        ))}
      </ul>

      <div className="mt-8 w-full space-y-3">
        <Button onClick={() => go('create')}>Create a new wallet</Button>
        <Button variant="ghost" onClick={() => go('import')}>I already have a recovery phrase</Button>
      </div>
    </div>
  )
}

/* ---------------- Create password ---------------- */
export function Create() {
  const { go, startSession } = useStore()
  const [p1, setP1] = useState('')
  const [p2, setP2] = useState('')
  const [ok, setOk] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    if (p1.length < 8) return setError('Password must be at least 8 characters')
    if (p1 !== p2) return setError('Passwords do not match')
    if (!ok) return setError('Please tick the box to continue')
    setBusy(true)
    try {
      startSession(await api.create(p1), 'srp')
    } catch (err) {
      setError(errMsg(err))
      setBusy(false)
    }
  }

  return (
    <Page title="Create a password" onBack={() => go('welcome')}
      subtitle="It unlocks the wallet on this computer only. It cannot recover your wallet.">
      <form onSubmit={submit} className="space-y-3">
        <Input label="New password" type="password" autoComplete="new-password"
               value={p1} onChange={(e) => setP1(e.target.value)} />
        <PasswordMeter value={p1} />
        <Input label="Confirm password" type="password" autoComplete="new-password"
               value={p2} onChange={(e) => setP2(e.target.value)} />
        <label className="flex items-start gap-2.5 pt-1 text-sm">
          <input type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)}
                 className="mt-0.5 size-4 accent-accent" />
          I understand that nobody can recover this password for me.
        </label>
        <div className="min-h-5 text-sm text-bad">{error}</div>
        <Button type="submit" loading={busy}>Create wallet</Button>
      </form>
    </Page>
  )
}

/* ---------------- Recovery phrase ---------------- */
export function Srp() {
  const { phrase, go } = useStore()
  const toast = useToast()
  const [shown, setShown] = useState(false)

  if (!phrase) {
    return (
      <Page title="Recovery phrase" subtitle="This phrase is only shown once, right after creation.">
        <Button onClick={() => go('home')}>Continue</Button>
      </Page>
    )
  }
  const words = phrase.split(' ')

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(phrase)
      toast('ok', 'Copied. Clear your clipboard after pasting it somewhere safe.')
    } catch {
      toast('bad', 'Copy failed')
    }
  }

  return (
    <Page title="Secret Recovery Phrase">
      <div className="flex gap-2.5 rounded-xl border border-warn/40 bg-warn/10 p-3 text-xs text-warn">
        <AlertTriangle className="mt-0.5 size-4 shrink-0" />
        Write these 12 words on paper, in order. Anyone who has them controls your funds,
        and without them your wallet cannot be recovered. Never share or screenshot them.
      </div>

      <div className="relative mt-4">
        <div className={cn('grid grid-cols-3 gap-2 transition', !shown && 'pointer-events-none select-none blur-md')}>
          {words.map((w, i) => (
            <motion.div key={i} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.02 }}
              className="rounded-lg border border-line bg-surface-2 px-2.5 py-2 font-mono text-sm">
              <span className="mr-1.5 text-[10px] text-dim">{i + 1}</span>{w}
            </motion.div>
          ))}
        </div>
        {!shown && (
          <button onClick={() => setShown(true)}
            className="absolute inset-0 grid place-items-center text-sm font-semibold">
            <span className="glass flex items-center gap-2 rounded-full px-4 py-2"><Eye className="size-4" /> Click to reveal</span>
          </button>
        )}
      </div>

      <div className="mt-5 space-y-3">
        <Button variant="ghost" onClick={copy} disabled={!shown}><Copy className="size-4" /> Copy to clipboard</Button>
        <Button disabled={!shown} onClick={() => go('quiz')}>I wrote it down</Button>
      </div>
    </Page>
  )
}

/* ---------------- Backup quiz ---------------- */
export function Quiz() {
  const { phrase, go, clearPhrase } = useStore()
  const toast = useToast()
  const [picks] = useState(() =>
    [...Array(12).keys()].sort(() => Math.random() - 0.5).slice(0, 3).sort((a, b) => a - b))
  const [vals, setVals] = useState(['', '', ''])
  const [error, setError] = useState('')

  if (!phrase) { return <Page title="Confirm your phrase"><Button onClick={() => go('home')}>Continue</Button></Page> }
  const words = phrase.split(' ')

  const check = (e: FormEvent) => {
    e.preventDefault()
    const good = picks.every((idx, k) => vals[k].trim().toLowerCase() === words[idx])
    if (!good) return setError('One or more words are wrong. Check your written copy.')
    clearPhrase()                     // the phrase leaves browser memory as soon as it is confirmed
    toast('ok', 'Backup confirmed. Your wallet is ready.')
    go('home')
  }

  return (
    <Page title="Confirm your phrase" onBack={() => go('srp')}
      subtitle="Type the words at these positions to prove you saved it.">
      <form onSubmit={check} className="space-y-3">
        {picks.map((idx, k) => (
          <Input key={idx} label={`Word #${idx + 1}`} autoComplete="off" spellCheck={false}
                 value={vals[k]} onChange={(e) => setVals((v) => v.map((x, j) => (j === k ? e.target.value : x)))} />
        ))}
        <div className="min-h-5 text-sm text-bad">{error}</div>
        <Button type="submit">Confirm</Button>
      </form>
    </Page>
  )
}

/* ---------------- Import ---------------- */
export function Import() {
  const { go, startSession } = useStore()
  const toast = useToast()
  const [phrase, setPhrase] = useState('')
  const [p1, setP1] = useState('')
  const [p2, setP2] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const count = phrase.trim().split(/\s+/).filter(Boolean).length

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    if (p1.length < 8) return setError('Password must be at least 8 characters')
    if (p1 !== p2) return setError('Passwords do not match')
    setBusy(true)
    try {
      const r = await api.restore(p1, phrase)
      startSession(r, 'home')
      if (r.discovered) toast('ok', `Recovered ${r.discovered} more account(s) used on-chain`)
    } catch (err) {
      setError(errMsg(err))
      setBusy(false)
    }
  }

  return (
    <Page title="Import a wallet" onBack={() => go('welcome')}
      subtitle="Enter your Secret Recovery Phrase and choose a password for this computer.">
      <form onSubmit={submit} className="space-y-3">
        <Textarea label="Secret Recovery Phrase" autoComplete="off" spellCheck={false}
                  placeholder="word1 word2 word3 …" value={phrase} onChange={(e) => setPhrase(e.target.value)} />
        <div className={cn('text-xs', count === 12 ? 'text-ok' : 'text-dim')}>{count} / 12 words</div>
        <Input label="New password" type="password" autoComplete="new-password"
               value={p1} onChange={(e) => setP1(e.target.value)} />
        <Input label="Confirm password" type="password" autoComplete="new-password"
               value={p2} onChange={(e) => setP2(e.target.value)} />
        <div className="min-h-5 text-sm text-bad">{error}</div>
        <Button type="submit" loading={busy}>Import wallet</Button>
      </form>
    </Page>
  )
}