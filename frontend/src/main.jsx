import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Analytics } from '@vercel/analytics/react'
import { SpeedInsights } from '@vercel/speed-insights/react'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
    {/* Both render nothing, and both are served first-party from /_vercel/*
        by Vercel: Analytics counts page views (cookieless), SpeedInsights
        reports Core Web Vitals measured on real visitors' devices. In dev
        each detects localhost and logs instead of sending. They live here
        rather than in App.jsx: app-shell plumbing, not planning UI. */}
    <Analytics />
    <SpeedInsights />
  </StrictMode>,
)
