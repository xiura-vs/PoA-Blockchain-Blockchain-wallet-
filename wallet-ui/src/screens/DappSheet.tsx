import { useEffect, useState } from 'react'
import { AlertTriangle, ArrowDown, Globe } from 'lucide-react'
import { api } from '../lib/api'
import type { DappRequest } from '../lib/types'
import { useStore } from '../store'
import { Avatar, Button } from '../components/ui'
import { useToast } from '../components/useToast'
import { Sheet } from '../components/sheet'
import { cn, fmtCoins, shortAddr } from '../lib/utils'
import { errMsg } from './helpers'

function Body({ req, onDone }: { req: DappRequest; onDone: () => void }) {
  const { accounts, selected, refreshAccounts } = useStore()
  const toast = useToast()
  const [picked, setPicked] = useState<string[]>(selected ? [selected] : [])
  const [busy, setBusy] = useState<'' | 'ok' | 'no'>('')
  const [error, setError] = useState('')

  const isConnect = req.type === 'connect'
  const p = req.params
  const nameOf = (a?: string) => accounts.find((x) => x.address === a)?.name ?? shortAddr(a ?? '')
  const toggle = (a: string) =>
    setPicked((x) => (x.includes(a) ? x.filter((y) => y !== a) : [...x, a]))

  const decide = async (approve: boolean) => {
    if (approve && isConnect && !picked.length) return setError('Select at least one account')
    setBusy(approve ? 'ok' : 'no')
    setError('')
    try {
      const r = await api.dappResolve(req.id, approve, approve && isConnect ? picked : undefined)
      if (r.status === 'failed') toast('bad', r.error ?? 'Request failed')
      else if (approve) toast('ok', isConnect ? 'Site connected' : 'Payment submitted')
    } catch (e) {
      toast('bad', errMsg(e))                 // e.g. the request expired while the sheet was open
    }
    await refreshAccounts()
    onDone()
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-bold">{isConnect ? 'Connect request' : 'Confirm transaction'}</h2>

      <div className="glass flex items-center gap-3 rounded-xl p-3">
        <Globe className="size-5 shrink-0 text-accent" />
        <div className="min-w-0">
          <div className="text-xs text-dim">Requested by</div>
          <div className="break-all font-mono text-sm font-semibold">{req.origin}</div>
        </div>
      </div>

      {isConnect ? (
        <>
          <p className="text-sm text-dim">
            This site wants to see your account address and ask you to approve payments.
          </p>
          <div className="space-y-2">
            {accounts.map((a) => (
              <button key={a.address} type="button" onClick={() => toggle(a.address)}
                className={cn('flex w-full items-center gap-3 rounded-xl border p-3 text-left transition',
                  picked.includes(a.address) ? 'border-accent bg-accent/10' : 'border-line hover:bg-surface-2')}>
                <Avatar address={a.address} size={32} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-semibold">{a.name}</div>
                  <div className="font-mono text-xs text-dim">{shortAddr(a.address)}</div>
                </div>
                <input type="checkbox" readOnly checked={picked.includes(a.address)} className="size-4 accent-accent" />
              </button>
            ))}
          </div>
          <div className="flex gap-2.5 rounded-xl border border-warn/40 bg-warn/10 p-3 text-xs text-warn">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            Only connect to sites you trust. A connected site can request payments, but it cannot move funds without your approval.
          </div>
        </>
      ) : (
        <div className="glass space-y-3 rounded-2xl p-4">
          <div className="flex items-center gap-3">
            <Avatar address={p.from ?? ''} size={32} />
            <div>
              <div className="text-xs text-dim">From</div>
              <div className="text-sm font-semibold">
                {nameOf(p.from)} <span className="font-mono text-xs font-normal text-dim">{shortAddr(p.from ?? '')}</span>
              </div>
            </div>
          </div>
          <ArrowDown className="mx-auto size-4 text-dim" />
          <div className="flex items-center gap-3">
            <Avatar address={p.to ?? ''} size={32} />
            <div className="min-w-0">
              <div className="text-xs text-dim">To</div>
              <div className="break-all font-mono text-xs">{p.to}</div>
            </div>
          </div>
          <div className="border-t border-line pt-3">
            <div className="text-xs text-dim">Amount</div>
            <div className="text-3xl font-bold tabular-nums">
              {fmtCoins(p.amount)} <span className="text-base font-medium text-dim">PC</span>
            </div>
          </div>
        </div>
      )}

      <div className="min-h-5 text-sm text-bad">{error}</div>
      <div className="space-y-2">
        <Button loading={busy === 'ok'} disabled={busy === 'no'} onClick={() => void decide(true)}>
          {isConnect ? 'Connect' : 'Confirm and sign'}
        </Button>
        <Button variant="ghost" loading={busy === 'no'} disabled={busy === 'ok'} onClick={() => void decide(false)}>
          Reject
        </Button>
      </div>
    </div>
  )
}

/** Polls the wallet service for requests filed by websites and shows them one at a time. */
export function DappPrompt() {
  const [req, setReq] = useState<DappRequest | null>(null)

  useEffect(() => {
    if (req) return                      // one request at a time; resume polling when it's handled
    let dead = false
    const poll = async () => {
      try {
        const r = await api.dappPending()
        if (!dead && r.requests[0]) setReq(r.requests[0])
      } catch { /* locked or offline: nothing to show */ }
    }
    const t = setInterval(() => void poll(), 1500)
    return () => { dead = true; clearInterval(t) }
  }, [req])

  // Backdrop clicks do nothing: the user must press Confirm or Reject.
  return (
    <Sheet open={!!req} onClose={() => {}}>
      {req && <Body key={req.id} req={req} onDone={() => setReq(null)} />}
    </Sheet>
  )
}