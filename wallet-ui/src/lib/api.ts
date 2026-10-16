import type {
  Account, ConnectedSite, DappRequest, HistoryItem, NetNode,
  SendResult, SessionResult, WalletState,
} from './types'

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

let token: string | null = sessionStorage.getItem('tok')
let lockedHandler: (() => void) | null = null

export const session = {
  get token() { return token },
  set(t: string | null) {
    token = t
    if (t) sessionStorage.setItem('tok', t)
    else sessionStorage.removeItem('tok')
  },
  onLocked(fn: () => void) { lockedHandler = fn },
}

async function request<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (token) headers['X-Session'] = token

  let res: Response
  try {
    res = await fetch(path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError('Wallet service unreachable', 0)
  }

  let data: unknown = {}
  try { data = await res.json() } catch { /* empty body */ }

  if (!res.ok) {
    const d = data as { error?: string; reason?: string }
    const msg = d.error ?? d.reason ?? `Request failed (${res.status})`
    if (res.status === 401 && msg === 'wallet is locked') lockedHandler?.()
    throw new ApiError(msg, res.status)
  }
  return data as T
}

const get = <T,>(path: string) => request<T>('GET', path)
const post = <T,>(path: string, body: unknown = {}) => request<T>('POST', path, body)

export const api = {
  // lifecycle
  state: () => get<WalletState>('/api/state'),
  create: (password: string) => post<SessionResult>('/api/create', { password }),
  restore: (password: string, mnemonic: string) =>
    post<SessionResult>('/api/restore', { password, mnemonic }),
  unlock: (password: string) => post<SessionResult>('/api/unlock', { password }),
  lock: () => post<{ ok: boolean }>('/api/lock'),
  ping: () => post<{ ok: boolean }>('/api/ping'),

  // accounts
  accounts: () => get<{ accounts: Account[] }>('/api/accounts'),
  addAccount: (name?: string) => post<Account>('/api/accounts/add', { name }),
  importKey: (private_key: string, name?: string) =>
    post<Account>('/api/accounts/import', { private_key, name }),
  rename: (address: string, name: string) =>
    post<{ ok: boolean }>('/api/accounts/rename', { address, name }),

  // chain
  history: (address: string) => get<HistoryItem[]>(`/api/history/${address}`),
  network: () => get<{ nodes: NetNode[] }>('/api/network'),
  send: (from: string, to: string, amount: number) =>
    post<SendResult>('/api/send', { from, to, amount }),

  // secrets (password-gated by the service)
  reveal: (password: string) => post<{ mnemonic: string }>('/api/reveal', { password }),
  exportKey: (address: string, password: string) =>
    post<{ private_key: string }>('/api/export', { address, password }),
  changePassword: (old: string, next: string) =>
    post<{ ok: boolean }>('/api/change_password', { old, new: next }),

  // dApp connections
  dappPending: () => get<{ requests: DappRequest[] }>('/api/dapp/pending'),
  dappResolve: (id: string, approve: boolean, accounts?: string[]) =>
    post<{ status: string; error?: string }>('/api/dapp/resolve', { id, approve, accounts }),
  dappSites: () => get<{ sites: ConnectedSite[] }>('/api/dapp/permissions'),
  dappRevoke: (origin: string) => post<{ ok: boolean }>('/api/dapp/revoke', { origin }),
}