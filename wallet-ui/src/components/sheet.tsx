import type { ReactNode } from 'react'
import { AnimatePresence, motion } from 'framer-motion'

/** Bottom sheet that slides up inside the wallet frame (the parent must be `relative`). */
export function Sheet({ open, onClose, children }: {
  open: boolean; onClose: () => void; children: ReactNode
}) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="overlay"
          className="absolute inset-0 z-40 flex items-end bg-black/55"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.div
            onClick={(e) => e.stopPropagation()}
            initial={{ y: '100%' }} animate={{ y: 0 }} exit={{ y: '100%' }}
            transition={{ type: 'spring', damping: 32, stiffness: 340 }}
            className="max-h-full w-full overflow-y-auto rounded-t-3xl border-t border-line bg-bg p-5"
          >
            <div className="mx-auto mb-4 h-1 w-10 rounded-full bg-line" />
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}