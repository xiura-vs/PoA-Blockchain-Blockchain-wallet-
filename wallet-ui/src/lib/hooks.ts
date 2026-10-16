import { useEffect, useRef, useState } from 'react'

/** Smoothly animates a number toward `target` (starts at the first value, no intro animation). */
export function useCountUp(target: number | null | undefined, ms = 700): number | null {
  const [shown, setShown] = useState(target ?? 0)
  const from = useRef(target ?? 0)

  useEffect(() => {
    if (target == null || from.current === target) return
    const start = from.current
    const t0 = performance.now()
    let raf = 0
    const tick = (now: number) => {
      const p = Math.min(1, (now - t0) / ms)
      const eased = 1 - Math.pow(1 - p, 3)             // ease-out
      const v = Math.round(start + (target - start) * eased)
      from.current = v
      setShown(v)
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, ms])

  return target == null ? null : shown
}