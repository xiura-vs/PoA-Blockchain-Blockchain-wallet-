import { useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowDown } from 'lucide-react'
import { api } from '../lib/api'
import type { Account } from '../lib/types'
import { Avatar, Button, Input } from '../components/ui'
import { useToast } from '../components/useToast'
import { fmtCoins, shortAddr } from '../lib/utils'
import { errMsg } from './helpers'

const ADDR = /^PC[0-9a-f]{40}$/

export function SendForm({ account, accounts, onSent }: {
  account: Account; accounts: Account[]; onSent: () => void
}) {
  const toast = useToast()
  const [step, setStep] = useState<'form' | 'review'>('form')
  const [to, setTo] = useState('')
  const [amt, setAmt] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const others = accounts.filter((a) => a.address !== account.address)
  const dest = to.trim()
  const destName = accounts.find((a) => a.address === dest)?.name
  const amount = Number(amt)

  const review = (e: FormEvent) => {
    e.preventDefault()
    setError('')
    if (!ADDR.test(dest)) return setError('Enter a valid address (PC + 40 hex characters)')
    if (!/^[1-9][0-9]{0,14}$/.test(amt)) return setError('Amount must be a positive whole number')
    if (account.balance != null && amount > account.balance) return setError('Insufficient funds')
    setStep('review')
  }

  const confirm = async () => {
    setBusy(true)
    setError('')
    try {
      await api.send(account.address, dest, amount)     // signed inside the wallet service
      toast('ok', 'Transaction submitted')
      onSent()
    } catch (err) {
      setError(errMsg(err))
      setBusy(false)
    }
  }

  if (step === 'review') {
    return (
      <div className="space-y-4">
        <h2 className="text-lg font-bold">Review</h2>
        <div className="glass space-y-3 rounded-2xl p-4">
          <div className="flex items-center gap-3">
            <Avatar address={account.address} size={32} />
            <div><div className="text-xs text-dim">From</div>
              <div className="text-sm font-semibold">{account.name} <span className="font-mono text-xs font-normal text-dim">{shortAddr(account.address)}</span></div></div>
          </div>
          <ArrowDown className="mx-auto size-4 text-dim" />
          <div className="flex items-center gap-3">
            <Avatar address={dest} size={32} />
            <div className="min-w-0"><div className="text-xs text-dim">To</div>
              <div className="text-sm font-semibold">{destName ?? 'External address'}</div>
              <div className="break-all font-mono text-xs text-dim">{dest}</div></div>
          </div>
          <div className="border-t border-line pt-3">
            <div className="text-xs text-dim">Amount</div>
            <div className="text-3xl font-bold tabular-nums">{fmtCoins(amount)} <span className="text-base font-medium text-dim">PC</span></div>
            <div className="mt-1 text-xs text-dim">Network fee: none (demo chain)</div>
          </div>
        </div>
        <p className="text-xs text-dim">
          The wallet signs this locally. Every node then checks the signature, nonce and balance independently.
        </p>
        <div className="min-h-5 text-sm text-bad">{error}</div>
        <div className="space-y-2">
          <Button loading={busy} onClick={() => void confirm()}>Confirm and sign</Button>
          <Button variant="ghost" disabled={busy} onClick={() => setStep('form')}>Back</Button>
        </div>
      </div>
    )
  }

  return (
    <form onSubmit={review} className="space-y-3">
      <Input label="To (address)" placeholder="PC…" autoComplete="off" spellCheck={false}
             value={to} onChange={(e) => setTo(e.target.value)} className="font-mono" />
      {others.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {others.map((a) => (
            <button type="button" key={a.address} onClick={() => setTo(a.address)}
              className="glass flex items-center gap-1.5 rounded-full py-1 pl-1 pr-3 text-xs hover:bg-surface-2">
              <Avatar address={a.address} size={20} />{a.name}
            </button>
          ))}
        </div>
      )}
      <div className="relative">
        <Input label="Amount (whole coins)" inputMode="numeric" placeholder="0" autoComplete="off"
               value={amt} onChange={(e) => setAmt(e.target.value.replace(/\D/g, '').slice(0, 15))} />
        {!!account.balance && (
          <button type="button" onClick={() => setAmt(String(account.balance))}
            className="absolute bottom-2.5 right-3 rounded-md bg-surface-2 px-2 py-0.5 text-xs font-semibold text-accent">
            Max
          </button>
        )}
      </div>
      <div className="text-xs text-dim">Available: {fmtCoins(account.balance)} PC · Network fee: none</div>
      <div className="min-h-5 text-sm text-bad">{error}</div>
      <Button type="submit">Review</Button>
    </form>
  )
}