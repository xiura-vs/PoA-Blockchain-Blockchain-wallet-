import { useCallback, useId, useState } from 'react'
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { AlertCircle, CheckCircle2, Loader2 } from 'lucide-react'
import { cn, hueFrom } from '../lib/utils'
import { ToastCtx } from './useToast'
import type { Push, ToastKind } from './useToast'

/* ---------- Button ---------- */
type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'ghost' | 'danger'
  loading?: boolean
}

export function Button({
  variant = 'primary', loading = false, className, children, disabled, ...rest
}: ButtonProps) {
  const styles = {
    primary: 'bg-accent text-accent-fg hover:brightness-110',
    ghost: 'border border-line text-fg hover:bg-surface-2',
    danger: 'bg-bad text-white hover:brightness-110',
  }[variant]
  return (
    <button
      disabled={disabled || loading}
      className={cn(
        'inline-flex w-full items-center justify-center gap-2 rounded-full px-5 py-3 text-sm font-semibold',
        'transition active:scale-[.98] disabled:cursor-not-allowed disabled:opacity-50',
        styles, className,
      )}
      {...rest}
    >
      {loading && <Loader2 className="size-4 animate-spin" />}
      {children}
    </button>
  )
}

/* ---------- Input ---------- */
type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  label?: string
  hint?: string
  error?: string
}

export function Input({ label, hint, error, className, id, ...rest }: InputProps) {
  const uid = useId()
  const fid = id ?? uid
  return (
    <div className="space-y-1.5">
      {label && <label htmlFor={fid} className="block text-xs font-medium text-dim">{label}</label>}
      <input
        id={fid}
        className={cn(
          'w-full rounded-xl border bg-surface-2 px-3.5 py-3 text-sm text-fg outline-none transition',
          'focus:border-accent focus:ring-2 focus:ring-accent/30',
          error ? 'border-bad' : 'border-line',
          className,
        )}
        {...rest}
      />
      {error ? <p className="text-xs text-bad">{error}</p>
        : hint ? <p className="text-xs text-dim">{hint}</p> : null}
    </div>
  )
}

/* ---------- Card / Frame / Skeleton / Avatar ---------- */
export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn('glass rounded-2xl p-4', className)}>{children}</div>
}

/** The wallet "window": a centered, phone-width glass panel. */
export function AppFrame({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-start justify-center p-4 sm:items-center sm:p-8">
      <div
        className="glass relative w-full max-w-[420px] overflow-hidden rounded-3xl"
        style={{ boxShadow: 'var(--shadow)' }}
      >
        {children}
      </div>
    </div>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-lg bg-surface-2', className)} />
}

/** Gradient avatar derived from the address (same address -> same colors, like a blockie). */
export function Avatar({ address, size = 36 }: { address: string; size?: number }) {
  const a = hueFrom(address)
  const b = hueFrom(address, 70)
  return (
    <div
      className="shrink-0 rounded-full ring-1 ring-white/20"
      style={{
        width: size,
        height: size,
        background: `linear-gradient(135deg, hsl(${a} 80% 62%), hsl(${b} 80% 42%))`,
      }}
    />
  )
}

/* ---------- Toasts ---------- */
type ToastItem = { id: number; kind: ToastKind; text: string }

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])

  const push = useCallback<Push>((kind, text) => {
    const id = Date.now() + Math.random()
    setItems((x) => [...x, { id, kind, text }])
    setTimeout(() => setItems((x) => x.filter((t) => t.id !== id)), 3500)
  }, [])

  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-5 z-50 flex flex-col items-center gap-2">
        <AnimatePresence>
          {items.map((t) => (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, y: 16, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8 }}
              className="glass pointer-events-auto flex items-center gap-2 rounded-full px-4 py-2.5 text-sm shadow-lg"
            >
              {t.kind === 'ok'
                ? <CheckCircle2 className="size-4 text-ok" />
                : <AlertCircle className="size-4 text-bad" />}
              {t.text}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastCtx.Provider>
  )
}