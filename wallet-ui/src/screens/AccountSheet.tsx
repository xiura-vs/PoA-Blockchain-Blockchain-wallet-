import { useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowLeft, Check, KeyRound, Pencil, Plus } from 'lucide-react'
import { api } from '../lib/api'
import { useStore } from '../store'
import { Avatar, Button, Input } from '../components/ui'
import { useToast } from '../components/useToast'
import { Sheet } from '../components/sheet'
import { cn, fmtCoins, shortAddr } from '../lib/utils'
import { errMsg } from './helpers'

type Mode = 'list' | 'create' | 'import' | 'rename'

function Body({ onClose }: { onClose: () => void }) {
  const { accounts, selected, select, refreshAccounts } = useStore()
  const toast = useToast()
  const [mode, setMode] = useState<Mode>('list')
  const [name, setName] = useState('')
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const current = accounts.find((a) => a.address === selected)

  const open = (m: Mode, initialName = '') => { setMode(m); setName(initialName); setKey(''); setError('') }

  const run = async (fn: () => Promise<void>) => {
    setBusy(true)
    setError('')
    try { await fn() } catch (e) { setError(errMsg(e)) } finally { setBusy(false) }
  }

  const create = (e: FormEvent) => {
    e.preventDefault()
    void run(async () => {
      const acc = await api.addAccount(name.trim() || undefined)
      await refreshAccounts()
      select(acc.address)
      toast('ok', `${acc.name} created`)
      onClose()
    })
  }
  const importKey = (e: FormEvent) => {
    e.preventDefault()
    void run(async () => {
      const acc = await api.importKey(key.trim(), name.trim() || undefined)
      await refreshAccounts()
      select(acc.address)
      toast('ok', `${acc.name} imported`)
      onClose()
    })
  }
  const rename = (e: FormEvent) => {
    e.preventDefault()
    if (!current) return
    void run(async () => {
      await api.rename(current.address, name)
      await refreshAccounts()
      toast('ok', 'Account renamed')
      onClose()
    })
  }

  if (mode === 'list') {
    return (
      <div className="space-y-2">
        <h2 className="mb-2 text-lg font-bold">My accounts</h2>
        {accounts.map((a) => (
          <button key={a.address} onClick={() => { select(a.address); onClose() }}
            className={cn('flex w-full items-center gap-3 rounded-xl border p-3 text-left transition',
              a.address === selected ? 'border-accent bg-accent/10' : 'border-line hover:bg-surface-2')}>
            <Avatar address={a.address} size={36} />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <span className="truncate">{a.name}</span>
                {a.kind === 'imported' &&
                  <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[10px] font-normal text-dim">imported</span>}
              </div>
              <div className="font-mono text-xs text-dim">{shortAddr(a.address)}</div>
            </div>
            <div className="text-sm font-semibold tabular-nums">{fmtCoins(a.balance)}</div>
            {a.address === selected && <Check className="size-4 text-accent" />}
          </button>
        ))}
        <div className="space-y-2 pt-3">
          <Button variant="ghost" onClick={() => open('create')}><Plus className="size-4" /> Create account</Button>
          <Button variant="ghost" onClick={() => open('import')}><KeyRound className="size-4" /> Import private key</Button>
          <Button variant="ghost" onClick={() => open('rename', current?.name ?? '')}><Pencil className="size-4" /> Rename current account</Button>
        </div>
      </div>
    )
  }

  const titles = { create: 'Create account', import: 'Import account', rename: 'Rename account' }
  const submit = mode === 'create' ? create : mode === 'import' ? importKey : rename

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="mb-1 flex items-center gap-3">
        <button type="button" onClick={() => open('list')} aria-label="Back"
          className="grid size-9 place-items-center rounded-full border border-line hover:bg-surface-2">
          <ArrowLeft className="size-4" />
        </button>
        <h2 className="text-lg font-bold">{titles[mode]}</h2>
      </div>

      {mode === 'create' && (
        <p className="text-sm text-dim">
          The next account is derived from your Secret Recovery Phrase, so restoring the phrase brings it back.
        </p>
      )}
      {mode === 'import' && (
        <>
          <div className="rounded-xl border border-warn/40 bg-warn/10 p-3 text-xs text-warn">
            Imported accounts are NOT covered by your Secret Recovery Phrase. Back up the private key separately.
          </div>
          <Input label="Private key (64 hex characters)" type="password" autoComplete="off"
                 value={key} onChange={(e) => setKey(e.target.value)} />
        </>
      )}
      <Input label={mode === 'rename' ? 'New name' : 'Name (optional)'} autoComplete="off"
             value={name} onChange={(e) => setName(e.target.value)} maxLength={40} />
      <div className="min-h-5 text-sm text-bad">{error}</div>
      <Button type="submit" loading={busy}>
        {mode === 'create' ? 'Create' : mode === 'import' ? 'Import' : 'Save'}
      </Button>
    </form>
  )
}

export function AccountSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  return <Sheet open={open} onClose={onClose}><Body onClose={onClose} /></Sheet>
}