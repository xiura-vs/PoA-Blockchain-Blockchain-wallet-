import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { AlertTriangle, Copy, EyeOff, Globe, KeyRound, Unlink } from 'lucide-react'
import { api } from '../lib/api'
import type { ConnectedSite } from '../lib/types'
import { useStore } from '../store'
import { Button, Card, Input, Skeleton } from '../components/ui'
import { useToast } from '../components/useToast'
import { shortAddr } from '../lib/utils'
import { Page, PasswordMeter } from './shared'
import { errMsg } from './helpers'

type Secret = { title: string; value: string; words: boolean }

export function Security() {
  const { go, accounts, selected } = useStore()
  const toast = useToast()
  const acct = accounts.find((a) => a.address === selected) ?? accounts[0]

  const [pw, setPw] = useState('')
  const [busy, setBusy] = useState<'' | 'phrase' | 'key'>('')
  const [error, setError] = useState('')
  const [secret, setSecret] = useState<Secret | null>(null)

  const [oldPw, setOldPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [cBusy, setCBusy] = useState(false)
  const [cErr, setCErr] = useState('')

  const [sites, setSites] = useState<ConnectedSite[] | null>(null)

  // Secrets hide themselves after 30 seconds (and vanish when you leave this screen).
  useEffect(() => {
    if (!secret) return
    const t = setTimeout(() => setSecret(null), 30_000)
    return () => clearTimeout(t)
  }, [secret])

  useEffect(() => {
    let dead = false
    api.dappSites()
      .then((r) => { if (!dead) setSites(r.sites) })
      .catch(() => { if (!dead) setSites([]) })
    return () => { dead = true }
  }, [])

  const reveal = async (kind: 'phrase' | 'key') => {
    setError('')
    setSecret(null)
    if (!pw) return setError('Enter your password first')
    if (kind === 'key' && !acct) return
    setBusy(kind)
    try {
      if (kind === 'phrase') {
        const r = await api.reveal(pw)
        setSecret({ title: 'Secret Recovery Phrase', value: r.mnemonic, words: true })
      } else {
        const r = await api.exportKey(acct.address, pw)
        setSecret({ title: `Private key · ${acct.name}`, value: r.private_key, words: false })
      }
      setPw('')
    } catch (e) {
      setError(errMsg(e))            // includes "incorrect password" and the throttle message
    } finally {
      setBusy('')
    }
  }

  const copySecret = async () => {
    if (!secret) return
    try { await navigator.clipboard.writeText(secret.value); toast('ok', 'Copied. Clear your clipboard afterwards.') }
    catch { toast('bad', 'Copy failed') }
  }

  const change = async (e: FormEvent) => {
    e.preventDefault()
    setCErr('')
    if (newPw.length < 8) return setCErr('New password must be at least 8 characters')
    setCBusy(true)
    try {
      await api.changePassword(oldPw, newPw)
      toast('ok', 'Password changed')
      setOldPw('')
      setNewPw('')
    } catch (err) {
      setCErr(errMsg(err))
    } finally {
      setCBusy(false)
    }
  }

  const disconnect = async (origin: string) => {
    try {
      await api.dappRevoke(origin)
      setSites((s) => s && s.filter((x) => x.origin !== origin))
      toast('ok', 'Site disconnected')
    } catch (err) {
      toast('bad', errMsg(err))
    }
  }

  const nameOf = (a: string) => accounts.find((x) => x.address === a)?.name ?? shortAddr(a)

  return (
    <Page title="Security" onBack={() => go('home')}>
      <div className="space-y-6">
        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Secrets</h2>
          <p className="text-xs text-dim">Enter your password to view them. Nobody else should ever see these.</p>
          <Input label="Password" type="password" autoComplete="current-password"
                 value={pw} onChange={(e) => setPw(e.target.value)} />
          <div className="grid grid-cols-2 gap-2">
            <Button variant="ghost" loading={busy === 'phrase'} onClick={() => void reveal('phrase')}>
              Recovery phrase
            </Button>
            <Button variant="ghost" loading={busy === 'key'} onClick={() => void reveal('key')}>
              <KeyRound className="size-4" /> Export key
            </Button>
          </div>
          <div className="min-h-5 text-sm text-bad">{error}</div>

          {secret && (
            <Card className="space-y-3">
              <div className="flex items-start gap-2 text-xs text-warn">
                <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                {secret.title}. Anyone with this controls the funds. Hides automatically in 30 seconds.
              </div>
              {secret.words ? (
                <div className="grid grid-cols-3 gap-2">
                  {secret.value.split(' ').map((w, i) => (
                    <div key={i} className="rounded-lg border border-line bg-surface-2 px-2 py-1.5 font-mono text-xs">
                      <span className="mr-1 text-[10px] text-dim">{i + 1}</span>{w}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="break-all rounded-lg border border-line bg-surface-2 p-3 font-mono text-xs">
                  {secret.value}
                </div>
              )}
              <div className="grid grid-cols-2 gap-2">
                <Button variant="ghost" onClick={() => void copySecret()}><Copy className="size-4" /> Copy</Button>
                <Button variant="ghost" onClick={() => setSecret(null)}><EyeOff className="size-4" /> Hide</Button>
              </div>
            </Card>
          )}
        </section>

        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Change password</h2>
          <form onSubmit={change} className="space-y-3">
            <Input label="Current password" type="password" autoComplete="current-password"
                   value={oldPw} onChange={(e) => setOldPw(e.target.value)} />
            <Input label="New password" type="password" autoComplete="new-password"
                   value={newPw} onChange={(e) => setNewPw(e.target.value)} />
            <PasswordMeter value={newPw} />
            <div className="min-h-5 text-sm text-bad">{cErr}</div>
            <Button type="submit" loading={cBusy} disabled={!oldPw || !newPw}>Change password</Button>
          </form>
        </section>

        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Connected sites</h2>
          {sites === null ? (
            <Skeleton className="h-14 w-full rounded-xl" />
          ) : sites.length === 0 ? (
            <p className="text-sm text-dim">No connected sites.</p>
          ) : (
            sites.map((s) => (
              <Card key={s.origin} className="flex items-center gap-3">
                <Globe className="size-5 shrink-0 text-accent" />
                <div className="min-w-0 flex-1">
                  <div className="break-all font-mono text-xs">{s.origin}</div>
                  <div className="text-xs text-dim">{s.accounts.map(nameOf).join(', ')}</div>
                </div>
                <button onClick={() => void disconnect(s.origin)}
                  className="flex items-center gap-1 rounded-full border border-line px-3 py-1.5 text-xs font-medium hover:bg-surface-2">
                  <Unlink className="size-3.5" /> Disconnect
                </button>
              </Card>
            ))
          )}
          <p className="text-xs text-dim">
            Connections are saved inside your encrypted vault, so they survive restarts. Disconnect any site you no longer trust.
          </p>
        </section>
      </div>
    </Page>
  )
}