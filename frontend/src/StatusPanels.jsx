import { useEffect, useState } from 'react'

// The results region's three non-result states. Loading and empty are
// designed moments (tile-backed); error is deliberately plainer — card,
// no tile — so the two are unmistakable for each other.

const LOADING_LABELS = [
  'Checking what’s open near you',
  'Fitting your time and money',
  'Putting the stops in order',
  'Still working — the optimizer is being thorough',
]
// Label schedule: advance each second, jump to the overrun line at 8s.
const LOADING_LABEL_AT_MS = [1000, 2000, 8000]

// The ~3s solver wait, narrated instead of spun through. The phase labels
// map to nothing in the backend — they are honest about the KIND of work,
// not its progress (which is unknowable; a stuck progress bar is worse
// than none). Announced once via App's status line, not per label.
function LoadingPanel() {
  const [phase, setPhase] = useState(0)
  useEffect(() => {
    const timers = LOADING_LABEL_AT_MS.map((ms, i) => setTimeout(() => setPhase(i + 1), ms))
    return () => timers.forEach(clearTimeout)
  }, [])
  return (
    <div className="status-panel tile">
      <span className="disc spin-disc" aria-hidden="true" />
      <p className="loading-label">{LOADING_LABELS[phase]}</p>
      <div className="skeleton-card" aria-hidden="true" />
      <div className="skeleton-card" aria-hidden="true" />
    </div>
  )
}

// An empty plan is a valid outcome, so it gets an answer, not an error
// tone — and the fix itself, as chips that re-run the search on tap.
function EmptyPanel({ onAddTime, onAddMoney }) {
  return (
    <div className="status-panel tile">
      <h2>Nothing fits — yet</h2>
      <p className="status-body">Your budgets are a little tight for this neighbourhood.</p>
      <div className="chips">
        <button type="button" className="chip" onClick={onAddTime}>
          +30 minutes
        </button>
        <button type="button" className="chip" onClick={onAddMoney}>
          +100.000 ₫
        </button>
      </div>
    </div>
  )
}

function ErrorPanel({ detail, onRetry }) {
  return (
    <div className="error-panel">
      <h2>Couldn’t reach the planner</h2>
      <p className="status-body">Check your connection and try again.</p>
      <button type="button" className="chip" onClick={onRetry}>
        Try again
      </button>
      <details className="error-detail">
        <summary>Technical details</summary>
        <p>{detail}</p>
      </details>
    </div>
  )
}

export { LoadingPanel, EmptyPanel, ErrorPanel }
