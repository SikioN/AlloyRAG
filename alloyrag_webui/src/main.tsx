import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import AppRouter from './AppRouter'
import './i18n.ts';
import 'katex/dist/katex.min.css';
// Import KaTeX extensions at app startup to ensure they are registered before any rendering
import 'katex/contrib/mhchem'; // Chemistry formulas: \ce{} and \pu{}
import 'katex/contrib/copy-tex'; // Allow copying rendered formulas as LaTeX source

async function enableMocking() {
  if (!import.meta.env.DEV) {
    return
  }

  const { worker } = await import('./mocks/browser')

  // `worker.start()` returns a Promise that resolves
  // when the Service Worker is up and ready to intercept requests.
  return worker.start({ onUnhandledRequest: 'bypass' })
}

enableMocking().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <AppRouter />
    </StrictMode>
  )
})
