import type { ReactNode, TextareaHTMLAttributes } from 'react'
import { ArrowLeft } from 'lucide-react'
import { cn } from '../lib/utils'
import { strength } from './helpers'

export function PasswordMeter({ value }: { value: string }) {
  const s = value ? Math.max(1, strength(value)) : 0
  const color = ['', 'bg-bad', 'bg-warn', 'bg-ok', 'bg-ok'][s]
  const label = ['', 'Weak', 'Fair', 'Good', 'Strong'][s]
  return (
    <div className="space-y-1">
      <div className="flex gap-1.5">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className={cn('h-1.5 flex-1 rounded-full transition-colors', i <= s ? color : 'bg-surface-2')} />
        ))}
      </div>
      <div className="h-4 text-xs text-dim">{label}</div>
    </div>
  )
}

export function Textarea({ label, className, ...rest }:
  TextareaHTMLAttributes<HTMLTextAreaElement> & { label?: string }) {
  return (
    <div className="space-y-1.5">
      {label && <div className="text-xs font-medium text-dim">{label}</div>}
      <textarea
        className={cn(
          'h-28 w-full resize-none rounded-xl border border-line bg-surface-2 px-3.5 py-3 text-sm text-fg',
          'outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/30', className)}
        {...rest}
      />
    </div>
  )
}

/** Standard screen layout: optional back button, title, subtitle, content. */
export function Page({ title, subtitle, onBack, children }: {
  title: string; subtitle?: ReactNode; onBack?: () => void; children: ReactNode
}) {
  return (
    <div className="px-6 pb-7 pt-5">
      {onBack && (
        <button onClick={onBack} aria-label="Back"
          className="mb-3 grid size-9 place-items-center rounded-full border border-line hover:bg-surface-2">
          <ArrowLeft className="size-4" />
        </button>
      )}
      <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
      {subtitle && <p className="mt-1.5 text-sm text-dim">{subtitle}</p>}
      <div className="mt-5">{children}</div>
    </div>
  )
}