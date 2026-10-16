import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'
import { initialTheme } from './theme'
import { ThemeProvider } from './ThemeProvider'
import { ToastProvider } from './components/ui'
import { StoreProvider } from './StoreProvider'

// Set the theme before the first paint so there is no flash of the wrong theme.
document.documentElement.dataset.theme = initialTheme()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <ToastProvider>
        <StoreProvider>
          <App />
        </StoreProvider>
      </ToastProvider>
    </ThemeProvider>
  </StrictMode>,
)