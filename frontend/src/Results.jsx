import { formatDuration, formatVnd } from './format'

// Deep link to the real Google Maps place page (photos, hours, reviews) —
// zero API calls, opens the Maps app on phones. Districts were abolished in
// the 2025 reorganization, so the query is name+city only; upgrades to
// query_place_id if the seed ever stores Google place ids.
function mapsHref(place) {
  const query = `${place.name}, Hồ Chí Minh City`
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`
}

// The results region: stop cards joined by travel-leg connectors, so the
// list reads as a route rather than a table of places. Hovering or
// focusing a card highlights its map pin (and vice versa) through the
// single hoveredStopId owned by App.

function StopCard({ stop, index, hot, onHoverStop }) {
  const enter = () => onHoverStop(stop.place.id)
  const leave = () => onHoverStop(null)
  return (
    <div
      className={hot ? 'stop-card is-hot' : 'stop-card'}
      tabIndex={0}
      onMouseEnter={enter}
      onMouseLeave={leave}
      onFocus={enter}
      onBlur={leave}
    >
      {/* Decorative: the ol already gives screen readers the position. */}
      <span className="disc stop-disc" aria-hidden="true">
        {index + 1}
      </span>
      <div>
        {/* lang="vi" so screen readers pronounce diacritics, not spell them. */}
        <h3 className="stop-name" lang="vi">
          {stop.place.name}
        </h3>
        <p className="stop-meta">
          <span className="chip-mini">{stop.place.category}</span>
          stay {stop.place.avg_minutes} min
          <a
            className="maps-link"
            href={mapsHref(stop.place)}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={`Open ${stop.place.name} in Google Maps`}
          >
            Google Maps ↗
          </a>
        </p>
      </div>
      {/* The only yolk on screen. Free places say so — a "0 ₫" money pill
          shouts about money that isn't there. */}
      <span className="price-pill">
        {stop.place.price_per_person_vnd === 0 ? 'free' : formatVnd(stop.place.price_per_person_vnd)}
      </span>
    </div>
  )
}

// Only rendered with at least one stop — App routes the empty case to
// EmptyPanel instead.
function Results({ itinerary, hoveredStopId, onHoverStop, onReset }) {
  return (
    <>
      <h2>Your route</h2>
      <ol className="route">
        {itinerary.stops.map((stop, index) => (
          // --stagger drives the entrance delay; capped so the whole
          // sequence stays under 240ms however long the route is.
          <li key={stop.place.id} style={{ '--stagger': Math.min(index, 2) }}>
            {/* A travel leg belongs to the gap BETWEEN two stops, so it
                renders as a connector row, not inside a card. The
                start→first-stop leg is only counted in the totals. */}
            {/* Adjacent stops can be 0.2 min apart — floor at 1 so the
                connector never claims a zero-minute ride. */}
            {index > 0 && (
              <p className="leg">
                {Math.max(1, Math.round(stop.travel_minutes_from_prev))} min ride
              </p>
            )}
            <StopCard stop={stop} index={index} hot={hoveredStopId === stop.place.id} onHoverStop={onHoverStop} />
          </li>
        ))}
      </ol>
      {/* Mobile home of "Start over" — a destructive-ish action doesn't
          belong in a sticky bar under someone's thumb. Hidden ≥960px. */}
      <button type="button" className="ghost-button results-reset" onClick={onReset}>
        Start over
      </button>
    </>
  )
}

// The ink footer: totals as text, the mint check never alone (icon + words),
// "Start over" at the right edge on desktop only.
function TotalsBar({ itinerary, onReset }) {
  const n = itinerary.stops.length
  return (
    <footer className="totals-bar">
      <p className="totals-line">
        {formatDuration(Math.round(itinerary.total_minutes))} ·{' '}
        {formatVnd(itinerary.total_cost_vnd)} · {n} {n === 1 ? 'stop' : 'stops'}
      </p>
      <p className="within-budget">
        <span className="check" aria-hidden="true">
          ✓
        </span>{' '}
        within budget
      </p>
      <button type="button" className="ghost-button bar-reset" onClick={onReset}>
        Start over
      </button>
    </footer>
  )
}

export { Results, TotalsBar }
