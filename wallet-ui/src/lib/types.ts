export interface WalletState {
  has_vault: boolean
  unlocked: boolean
  autolock_seconds: number
}

export interface Account {
  name: string
  kind: 'hd' | 'imported'
  address: string
  balance?: number | null
  pending?: number | null
}

export interface HistoryItem {
  id: string
  from: string
  to: string
  amount: number
  nonce: number
  status: 'pending' | 'confirmed'
  block: number | null
  ts: number | null
  proposer: string | null
}

export interface NetNode {
  name: string
  up: boolean
  height?: number
  peers?: number
}

export interface SessionResult {
  token: string
  accounts: Account[]
  mnemonic?: string
  discovered?: number
}

export interface SendResult {
  ok: boolean
  reason: string | null
  tx_id: string
}

export interface DappRequest {
  id: string
  origin: string
  type: 'connect' | 'send_tx'
  params: { from?: string; to?: string; amount?: number }
}

export interface ConnectedSite {
  origin: string
  accounts: string[]
}