import { AnimatePresence, motion } from 'framer-motion'
import { Link2, Moon, Sun } from 'lucide-react'
import { useStore } from './store'
import { useTheme } from './theme'
import { AppFrame, Button, Skeleton } from './components/ui'
import { Create, Import, Quiz, Srp, Welcome } from './screens/Onboarding'
import { Lock } from './screens/Lock'
import { Home } from './screens/Home'
import { Security } from './screens/Security'
import { DappPrompt } from './screens/DappSheet'

function Loading() {
  return (
    <div className="space-y-3 p-6">
      <Skeleton className="h-8 w-40" /><Skeleton className="h-4 w-64" /><Skeleton className="h-24 w-full" />
    </div>
  )
}

function Offline() {
  const { retryBoot } = useStore()
  return (
    <div className="space-y-3 p-6 text-center">
      <h1 className="text-xl font-bold">Wallet service unreachable</h1>
      <p className="text-sm text-dim">
        Start it with <span className="font-mono">python -m mm_wallet.service</span> and try again.
      </p>
      <Button onClick={retryBoot}>Retry</Button>
    </div>
  )
}

export default function App() {
  const { screen } = useStore()
  const { theme, toggle } = useTheme()

  const view = {
    loading: <Loading />, offline: <Offline />, welcome: <Welcome />, create: <Create />,
    srp: <Srp />, quiz: <Quiz />, import: <Import />, lock: <Lock />, home: <Home />,
    security: <Security />,
  }[screen]

  return (
    <AppFrame>
      <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
        <div className="flex items-center gap-2 font-semibold">
          <Link2 className="size-5 text-accent" /> PoA Wallet
        </div>
        <button onClick={toggle} aria-label="Toggle theme"
          className="grid size-9 place-items-center rounded-full border border-line hover:bg-surface-2">
          {theme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
        </button>
      </div>
      <AnimatePresence mode="wait">
        <motion.div key={screen} initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -16 }} transition={{ duration: 0.18 }}>
          {view}
        </motion.div>
      </AnimatePresence>
      {/* Mounted only while signed in, so a locked wallet can never show an approval. */}
      {(screen === 'home' || screen === 'security') && <DappPrompt />}
    </AppFrame>
  )
}