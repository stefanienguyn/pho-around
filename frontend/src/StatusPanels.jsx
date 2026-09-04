import { useEffect, useState } from 'react'
import { useT } from './i18n'

// The results region's three non-result states. Loading and empty are
// designed moments (tile-backed); error is deliberately plainer — card,
// no tile — so the two are unmistakable for each other.

// Label schedule: advance each second, jump to the overrun line at 8s.
const LOADING_LABEL_AT_MS = [1000, 2000, 8000]

// The ~3s solver wait, narrated instead of spun through. The phase labels
// map to nothing in the backend — they are honest about the KIND of work,
// not its progress (which is unknowable; a stuck progress bar is worse
// than none). Announced once via App's status line, not per label.
function LoadingPanel() {
  const t = useT()
  const [phase, setPhase] = useState(0)
  useEffect(() => {
    const timers = LOADING_LABEL_AT_MS.map((ms, i) => setTimeout(() => setPhase(i + 1), ms))
    return () => timers.forEach(clearTimeout)
  }, [])
  return (
    <div className="status-panel tile">
      <span className="disc spin-disc" aria-hidden="true" />
      <p className="loading-label">{t.loadingLabels[phase]}</p>
      <div className="skeleton-card" aria-hidden="true" />
      <div className="skeleton-card" aria-hidden="true" />
    </div>
  )
}

// An empty plan is a valid outcome, so it gets an answer, not an error
// tone — and the fix itself, as chips that re-run the search on tap.
function EmptyPanel({ onAddTime, onAddMoney }) {
  const t = useT()
  return (
    <div className="status-panel tile">
      <h2>{t.emptyTitle}</h2>
      <p className="status-body">{t.emptyBody}</p>
      <div className="chips">
        <button type="button" className="chip" onClick={onAddTime}>
          {t.addTime}
        </button>
        <button type="button" className="chip" onClick={onAddMoney}>
          {t.addMoney}
        </button>
      </div>
    </div>
  )
}

function ErrorPanel({ detail, onRetry }) {
  const t = useT()
  return (
    <div className="error-panel">
      <h2>{t.errorTitle}</h2>
      <p className="status-body">{t.errorBody}</p>
      <button type="button" className="chip" onClick={onRetry}>
        {t.retry}
      </button>
      <details className="error-detail">
        <summary>{t.errorDetails}</summary>
        <p>{detail}</p>
      </details>
    </div>
  )
}

export { LoadingPanel, EmptyPanel, ErrorPanel }
