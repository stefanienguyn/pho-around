import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Analytics } from '@vercel/analytics/react'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
    {/* Cookieless page-view counter, served first-party from
        /_vercel/insights/* by Vercel. Renders nothing; in dev it detects
        localhost and logs instead of sending. Lives here rather than in
        App.jsx because it's app-shell plumbing, not planning UI. */}
    <Analytics />
  </StrictMode>,
)
