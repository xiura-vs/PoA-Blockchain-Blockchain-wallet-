import { ApiError } from '../lib/api'

export const errMsg = (e: unknown) =>
  e instanceof ApiError ? e.message : 'Something went wrong. Please try again.'

/** 0-4 */
export function strength(pw: string): number {
  let s = 0
  if (pw.length >= 8) s++
  if (pw.length >= 12) s++
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) s++
  if (/\d/.test(pw) && /[^A-Za-z0-9]/.test(pw)) s++
  return s
}