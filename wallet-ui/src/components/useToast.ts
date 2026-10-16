import { createContext, useContext } from 'react'

export type ToastKind = 'ok' | 'bad'
export type Push = (kind: ToastKind, text: string) => void

export const ToastCtx = createContext<Push>(() => {})
export const useToast = () => useContext(ToastCtx)