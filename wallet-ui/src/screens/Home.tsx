import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import type { LucideIcon } from 'lucide-react'
import {
  ArrowDownLeft, ArrowUpRight, ChevronDown, Copy, History, Inbox, Lock, QrCode, Repeat,
  Send as SendIcon, Shield,
} from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { api } from '../lib/api'
import type { Account, HistoryItem, NetNode } from '../lib/types'
import { useStore } from '../store'
import { Avatar, Button, Skeleton } from '../components/ui'
import { useToast } from '../components/useToast'
import { useCountUp } from '../lib/hooks'
import { cn, fmtCoins, shortAddr } from '../lib/utils'
import { AccountSheet } from './AccountSheet'
import { SendForm } from './Send'

type Tab = 'activity' | 'send' | 'receive'
const TABS: { id: Tab; label: string; icon: LucideIcon }[] = [
  { id: 'activity', label: 'Activity', icon: History },
  { id: 'send', label: 'Send', icon: SendIcon },
  { id: 'receive', label: 'Receive', icon: QrCode },
]

/* ---------- small pieces ---------- */
function NetPill({ net }: { net: NetNode[] | null }) {
  if (!net) return <Skeleton className="h-7 w-28 rounded-full" />
  const up = net.filter((n) => n.up)
  const height = Math.max(0, ...up.map((n) => n.height ?? 0))
  const color = up.length === net.length ? 'bg-ok' : up.length ? 'bg-warn' : 'bg-bad'
  return (
    <div className="glass flex items-center gap-2 rounded-full px-3 py-1.5 text-xs text-dim">
      <span className="relative flex size-2">
        <span className={cn('absolute inline-flex h-full w-full animate-ping rounded-full opacity-60', color)} />
        <span className={cn('relative inline-flex size-2 rounded-full', color)} />
      </span>
      {up.length ? `${up.length}/${net.length} nodes · block ${height}` : 'No nodes online'}
    </div>
  )
}

function BalanceCard({ account, onCopy }: { account: Account; onCopy: () => void }) {
  const shown = useCountUp(account.balance)
  return (
    <div className="rounded-2xl border border-line p-5 text-center"
      style={{ background: 'linear-gradient(135deg, color-mix(in srgb, var(--accent) 26%, transparent), color-mix(in srgb, #f472b6 14%, transparent))' }}>
      <button onClick={onCopy}
        className="mx-auto flex items-center gap-1.5 font-mono text-xs text-dim transition hover:text-fg">
        {shortAddr(account.address)} <Copy className="size-3" />
      </button>
      <div className="mt-2 text-4xl font-bold tracking-tight tabular-nums">
        {shown == null ? '—' : fmtCoins(shown)}
        <span className="ml-1.5 text-base font-medium text-dim">PC</span>
      </div>
      <div className="mt-1 h-4 text-xs text-warn">
        {account.pending ? `${account.pending} transaction(s) pending…` : ''}
      </div>
    </div>
  )
}

function ActivityList({ items, me, nameOf }: {
  items: HistoryItem[] | null; me: string; nameOf: (a: string) => string
}) {
  if (!items) {
    return <div className="space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-16 w-full rounded-xl" />)}</div>
  }
  if (!items.length) {
    return (
      <div className="flex flex-col items-center gap-2 py-8 text-center text-dim">
        <Inbox className="size-8" />
        <div className="text-sm font-medium text-fg">No transactions yet</div>
        <div className="text-xs">Send or receive coins and they will appear here.</div>
      </div>
    )
  }
  return (
    <div className="space-y-2">
      {items.map((t) => {
        const out = t.from === me
        const self = t.from === t.to
        const pending = t.status === 'pending'
        const peer = out ? t.to : t.from
        const Icon = self ? Repeat : out ? ArrowUpRight : ArrowDownLeft
        return (
          <motion.div key={t.id} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            className="glass flex items-center gap-3 rounded-xl p-3">
            <div className={cn('grid size-9 shrink-0 place-items-center rounded-full',
              pending ? 'bg-warn/15 text-warn' : out || self ? 'bg-surface-2 text-fg' : 'bg-ok/15 text-ok')}>
              <Icon className="size-4" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold">
                {self ? 'Self transfer' : out ? 'Sent' : 'Received'}{' '}
                <span className="font-normal text-dim">{out ? 'to' : 'from'} {nameOf(peer)}</span>
              </div>
              <div className="text-xs">
                {pending
                  ? <span className="text-warn">● Pending…</span>
                  : <span className="text-dim"><span className="text-ok">Confirmed</span> · block {t.block}{t.proposer ? ` · ${t.proposer}` : ''}</span>}
              </div>
            </div>
            <div className={cn('text-sm font-semibold tabular-nums', !out && !self && 'text-ok')}>
              {self ? '' : out ? '−' : '+'}{fmtCoins(t.amount)}
            </div>
          </motion.div>
        )
      })}
    </div>
  )
}

function Receive({ account, onCopy }: { account: Account; onCopy: () => void }) {
  return (
    <div className="flex flex-col items-center gap-4">
      <div className="rounded-2xl bg-white p-3">
        <QRCodeSVG value={account.address} size={168} />
      </div>
      <div className="text-center">
        <div className="text-sm font-semibold">{account.name}</div>
        <div className="mt-1 break-all font-mono text-xs text-dim">{account.address}</div>
      </div>
      <Button variant="ghost" onClick={onCopy}><Copy className="size-4" /> Copy address</Button>
      <p className="text-center text-xs text-dim">Only send PoA Coin (PC) to this address.</p>
    </div>
  )
}

/* ---------- the screen ---------- */
export function Home() {
  const { accounts, selected, refreshAccounts, lockNow, idleLeft, go } = useStore()
  const toast = useToast()
  const [tab, setTab] = useState<Tab>('activity')
  const [sheet, setSheet] = useState(false)
  const [net, setNet] = useState<NetNode[] | null>(null)
  const [hist, setHist] = useState<{ addr: string; items: HistoryItem[] } | null>(null)
  const [bump, setBump] = useState(0)
  const [left, setLeft] = useState(() => idleLeft())
  const seenPending = useRef(new Set<string>())

  const acct = accounts.find((a) => a.address === selected) ?? accounts[0]
  const addr = acct?.address
  const items = hist && hist.addr === addr ? hist.items : null
  const nameOf = (a: string) => accounts.find((x) => x.address === a)?.name ?? shortAddr(a)

  // balances + network status
  useEffect(() => {
    let dead = false
    const loadNet = async () => {
      try { const r = await api.network(); if (!dead) setNet(r.nodes) } catch { /* keep last value */ }
    }
    void refreshAccounts()
    void loadNet()
    const a = setInterval(() => void refreshAccounts(), 4000)
    const n = setInterval(() => void loadNet(), 6000)
    return () => { dead = true; clearInterval(a); clearInterval(n) }
  }, [refreshAccounts])

  // transaction history of the selected account (+ "confirmed" toast for txs we saw pending)
  useEffect(() => {
    if (!addr) return
    let dead = false
    const load = async () => {
      try {
        const list = await api.history(addr)
        if (dead) return
        for (const t of list) {
          if (t.status === 'confirmed' && seenPending.current.has(t.id)) {
            toast('ok', `Transaction confirmed in block ${t.block}`)
          }
        }
        seenPending.current = new Set(list.filter((t) => t.status === 'pending').map((t) => t.id))
        setHist({ addr, items: list })
      } catch { /* keep last value */ }
    }
    void load()
    const t = setInterval(() => void load(), 3000)
    return () => { dead = true; clearInterval(t) }
  }, [addr, bump, toast])

  // auto-lock countdown
  useEffect(() => {
    const t = setInterval(() => setLeft(idleLeft()), 1000)
    return () => clearInterval(t)
  }, [idleLeft])

  if (!acct) {
    return <div className="space-y-3 p-6"><Skeleton className="h-10 w-48" /><Skeleton className="h-32 w-full" /></div>
  }

  const copyAddress = async () => {
    try { await navigator.clipboard.writeText(acct.address); toast('ok', 'Address copied') }
    catch { toast('bad', 'Copy failed') }
  }

  return (
    <div className="relative min-h-[620px] overflow-hidden">
      <div className="space-y-4 px-5 pb-4 pt-4">
        <div className="flex items-center justify-between gap-2">
          <button onClick={() => setSheet(true)}
            className="glass flex min-w-0 items-center gap-2 rounded-full py-1.5 pl-1.5 pr-3 text-sm font-semibold">
            <Avatar address={acct.address} size={28} />
            <span className="truncate">{acct.name}</span>
            <ChevronDown className="size-4 shrink-0 text-dim" />
          </button>
          <NetPill net={net} />
        </div>
        <BalanceCard key={acct.address} account={acct} onCopy={() => void copyAddress()} />
      </div>

      <div className="flex border-b border-line px-2">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button key={id} onClick={() => setTab(id)}
            className={cn('relative flex flex-1 items-center justify-center gap-1.5 py-3 text-sm font-medium transition',
              tab === id ? 'text-accent' : 'text-dim hover:text-fg')}>
            <Icon className="size-4" />{label}
            {tab === id && (
              <motion.div layoutId="tabline" className="absolute inset-x-3 -bottom-px h-0.5 rounded bg-accent" />
            )}
          </button>
        ))}
      </div>

      <div className="px-5 py-4">
        <AnimatePresence mode="wait">
          <motion.div key={tab + (tab === 'activity' ? '' : acct.address)}
            initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}>
            {tab === 'activity' && <ActivityList items={items} me={acct.address} nameOf={nameOf} />}
            {tab === 'send' && (
              <SendForm account={acct} accounts={accounts}
                        onSent={() => { setTab('activity'); setBump((b) => b + 1) }} />
            )}
            {tab === 'receive' && <Receive account={acct} onCopy={() => void copyAddress()} />}
          </motion.div>
        </AnimatePresence>
      </div>

      <div className="flex items-center justify-between border-t border-line px-5 py-3 text-xs text-dim">
        <span>Auto-lock in {Math.floor(left / 60)}:{String(left % 60).padStart(2, '0')}</span>
        <div className="flex gap-2">
          <button onClick={() => go('security')}
            className="flex items-center gap-1.5 rounded-full border border-line px-3 py-1.5 font-medium text-fg hover:bg-surface-2">
            <Shield className="size-3.5" /> Security
          </button>
          <button onClick={() => void lockNow()}
            className="flex items-center gap-1.5 rounded-full border border-line px-3 py-1.5 font-medium text-fg hover:bg-surface-2">
            <Lock className="size-3.5" /> Lock
          </button>
        </div>
      </div>

      <AccountSheet open={sheet} onClose={() => setSheet(false)} />
    </div>
  )
}