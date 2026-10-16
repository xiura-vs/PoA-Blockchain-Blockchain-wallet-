export const cn = (...parts: (string | false | null | undefined)[]) =>
  parts.filter(Boolean).join(' ')

export const shortAddr = (a: string) => (a ? `${a.slice(0, 8)}…${a.slice(-4)}` : '')

/** Deterministic 0-359 hue from an address (used for the gradient avatar). */
export function hueFrom(addr: string, offset = 0): number {
  let h = 0
  for (const c of addr) h = (h * 31 + c.charCodeAt(0)) >>> 0
  return (h + offset) % 360
}

export const fmtCoins = (n: number | null | undefined) =>
  n == null ? '—' : n.toLocaleString('en-US')