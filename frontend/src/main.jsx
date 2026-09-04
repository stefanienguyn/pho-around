import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Analytics } from '@vercel/analytics/react'
import { SpeedInsights } from '@vercel/speed-insights/react'
import About from './About.jsx'
import App from './App.jsx'

// Two pages, no router: the server returns this same bundle for every URL
// (Vite dev falls back to index.html; in production vercel.json's rewrite
// does the same), so "which page" is just the pathname read once at load.
// Links between the pages are plain <a> tags — a full page load, which is
// fine at this scale. Reach for react-router when pages multiply.
const page = window.location.pathname === '/about' ? <About /> : <App />

createRoot(document.getElementById('root')).render(
  <StrictMode>
    {page}
    {/* Both render nothing, and both are served first-party from /_vercel/*
        by Vercel: Analytics counts page views (cookieless), SpeedInsights
        reports Core Web Vitals measured on real visitors' devices. In dev
        each detects localhost and logs instead of sending. They live here
        rather than in App.jsx: app-shell plumbing, not planning UI. */}
    <Analytics />
    <SpeedInsights />
  </StrictMode>,
)
