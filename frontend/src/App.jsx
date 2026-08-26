import { useState } from 'react'
import AskBox from './AskBox'
import MapView from './MapView'
import PlanForm from './PlanForm'
import { Results, TotalsBar } from './Results'
import { LoadingPanel, EmptyPanel, ErrorPanel } from './StatusPanels'
import { formatDurationLong, formatVndSpoken } from './format'
import './App.css'

// Launch state: no start set — the map invites a tap. Time/money open on
// the 2h / 200k presets. (The old District 1 benchmark start reproduces
// via "Enter coordinates instead": 10.7797, 106.6990.)
const DEFAULT_TIME_MIN = '120'
const DEFAULT_MONEY_VND = '200000'

// Where the backend lives — different per environment, so it comes from
// configuration rather than the code. Vite substitutes import.meta.env at
// BUILD time (the value is baked into the bundle), which is why changing it
// means a redeploy, not a restart. Defaults to the local backend so
// `npm run dev` works with no setup.
const API_BASE = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'
const API_URL = `${API_BASE}/api/itinerary`
const INTERPRET_URL = `${API_BASE}/api/interpret`

function App() {
  // Inputs always yield strings; keep state as strings and convert to
  // numbers only when building the API payload (the boundary).
  const [lat, setLat] = useState('')
  const [lng, setLng] = useState('')
  const [timeMin, setTimeMin] = useState(DEFAULT_TIME_MIN)
  const [moneyVnd, setMoneyVnd] = useState(DEFAULT_MONEY_VND)
  // Start-point mode: while true, map clicks set the start (crosshair +
  // hint pill). A map click or "Move" toggles it.
  const [picking, setPicking] = useState(true)
  // Bumped when Plan is pressed with no start; MapView shakes the hint
  // pill and takes focus so the map explains instead of a mute refusal.
  const [nudge, setNudge] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  // null = not asked yet; an object with empty stops = asked, nothing fits.
  const [itinerary, setItinerary] = useState(null)
  // The card ↔ map-pin hover link: one id, two listeners, two views.
  const [hoveredStopId, setHoveredStopId] = useState(null)

  const hasResults = itinerary !== null && itinerary.stops.length > 0

  function handleReset() {
    setItinerary(null)
    setError(null)
    setHoveredStopId(null)
  }

  // Locating = the browser is still asking the device; geoNote = a friendly
  // explanation when location didn't work (denied/unavailable/timeout).
  // What the person asked for in words, and what we understood it to mean.
  // The constraint list IS this feature's memory: it rides along on the next
  // interpret call so a follow-up ("make it 2 coffees") edits it instead of
  // starting over — no server-side session, nothing stored anywhere.
  const [ask, setAsk] = useState('')
  const [constraints, setConstraints] = useState([])
  const [askReply, setAskReply] = useState(null)
  const [askDropped, setAskDropped] = useState(0)
  const [asking, setAsking] = useState(false)
  const [askError, setAskError] = useState(null)
  const [locating, setLocating] = useState(false)
  const [geoNote, setGeoNote] = useState(null)

  // Map clicks arrive as raw floats; 5 decimals ≈ 1 m — plenty for a start pin.
  function handlePickStart(pickedLat, pickedLng) {
    setLat(pickedLat.toFixed(5))
    setLng(pickedLng.toFixed(5))
    setPicking(false)
    setGeoNote(null)
  }

  // The browser's built-in Geolocation API — no Google, no key. The browser
  // itself asks the user for permission; a "no" is a normal outcome (note +
  // the map-tap path), never an error state.
  function handleUseLocation() {
    if (!('geolocation' in navigator)) {
      setGeoNote('Location isn’t available in this browser — tap the map instead.')
      return
    }
    setLocating(true)
    setGeoNote(null)
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLocating(false)
        handlePickStart(position.coords.latitude, position.coords.longitude)
      },
      () => {
        setLocating(false)
        setGeoNote('Couldn’t get your location — tap the map instead.')
      },
      // High accuracy = GPS on phones; the timeout keeps the button from
      // spinning forever indoors.
      { enableHighAccuracy: true, timeout: 10000 }
    )
  }

  // The one path to the API. Budgets arrive as arguments (not read from
  // state) so callers that just changed them — the empty panel's
  // adjustment chips — aren't racing React's async state updates.
  // Words -> constraints. Deliberately does NOT plan: /api/itinerary stays a
  // pure function of its input, so the solver never depends on a model call.
  async function runInterpret(message) {
    setAsking(true)
    setAskError(null)
    try {
      const res = await fetch(INTERPRET_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, constraints }),
      })
      if (!res.ok) {
        // 503 means the feature simply isn't switched on in this deployment;
        // the sliders still work, so say that rather than showing a failure.
        throw new Error(
          res.status === 503
            ? "Asking isn't switched on here — use the sliders"
            : "Couldn't read that — try again, or use the sliders",
        )
      }
      const data = await res.json()
      setConstraints(data.constraints)
      setAskReply(data.reply)
      setAskDropped(data.dropped)
      setAsk('')
      // Re-plan straight away when there's somewhere to start from, so the
      // route visibly answers the sentence.
      if (lat && lng) {
        runPlan(Number(timeMin), Number(moneyVnd), data.constraints)
      }
    } catch (err) {
      setAskError(err.message)
    } finally {
      setAsking(false)
    }
  }

  function clearConstraints() {
    setConstraints([])
    setAskReply(null)
    setAskDropped(0)
    if (lat && lng) {
      runPlan(Number(timeMin), Number(moneyVnd), [])
    }
  }

  async function runPlan(timeBudgetMin, moneyBudgetVnd, withConstraints = constraints) {
    setLoading(true)
    setError(null)
    setItinerary(null)
    try {
      const res = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          start: { lat: Number(lat), lng: Number(lng) },
          time_budget_min: timeBudgetMin,
          money_budget_vnd: moneyBudgetVnd,
          constraints: withConstraints,
        }),
      })
      // fetch only rejects when no response happened at all (network, CORS);
      // an HTTP error status resolves normally and must be checked here.
      if (!res.ok) {
        throw new Error(`API error ${res.status}`)
      }
      const data = await res.json()
      setItinerary(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  function handleSubmit(event) {
    event.preventDefault()
    if (!Number.isFinite(parseFloat(lat)) || !Number.isFinite(parseFloat(lng))) {
      setNudge((n) => n + 1)
      return
    }
    runPlan(Number(timeMin), Number(moneyVnd))
  }

  // Empty-panel chips: bump the budget in the form AND re-run with the
  // bumped value — the fix, not a diagnosis.
  function handleAddTime() {
    const next = Number(timeMin) + 30
    setTimeMin(String(next))
    runPlan(next, Number(moneyVnd))
  }

  function handleAddMoney() {
    const next = Number(moneyVnd) + 100000
    setMoneyVnd(String(next))
    runPlan(Number(timeMin), next)
  }

  // The hero yields once anything occupies the results region (loading,
  // results, or the empty panel) and stays collapsed across re-plans —
  // expanding mid-flow would jump the layout against the sticky map.
  const heroCollapsed = loading || itinerary !== null

  // One screen-reader announcement per state change — never per loading
  // label. Rendered into the visually-hidden role="status" line below.
  let announcement = ''
  if (loading) {
    announcement = 'Planning your route'
  } else if (error) {
    announcement = 'Couldn’t reach the planner'
  } else if (itinerary) {
    announcement = hasResults
      ? `${itinerary.stops.length} stops, ${formatDurationLong(
          Math.round(itinerary.total_minutes)
        )}, ${formatVndSpoken(itinerary.total_cost_vnd)}`
      : 'No plan fits your budgets'
  }

  // Three page regions (hero / plan / results) + the map. DOM order puts
  // the form before the map so tab order starts at the inputs; CSS places
  // the map visually (pinned on top for phones, right column on desktop).
  return (
    <>
      <header className={heroCollapsed ? 'hero tile has-results' : 'hero tile'}>
        <h1>Phở around</h1>
        <p className="subline">Tell us where you are and how long you've got.</p>
        {/* The route ribbon: a miniature of the product's output, introducing
            the stool disc before the user has any data. Decorative. */}
        <div className="ribbon" aria-hidden="true">
          <span className="disc">1</span>
          <span className="disc">2</span>
          <span className="disc">3</span>
        </div>
      </header>
      <main className="content">
        <section className="plan">
          <PlanForm
            lat={lat}
            lng={lng}
            onLatChange={setLat}
            onLngChange={setLng}
            timeMin={timeMin}
            onTimeChange={setTimeMin}
            moneyVnd={moneyVnd}
            onMoneyChange={setMoneyVnd}
            picking={picking}
            onMove={() => setPicking(true)}
            locating={locating}
            geoNote={geoNote}
            onUseLocation={handleUseLocation}
            loading={loading}
            onSubmit={handleSubmit}
          />
          <AskBox
            value={ask}
            onChange={setAsk}
            onSubmit={runInterpret}
            asking={asking}
            reply={askReply}
            constraints={constraints}
            dropped={askDropped}
            error={askError}
            onClear={clearConstraints}
          />
        </section>
        <div className="map-region">
          <MapView
            startLat={parseFloat(lat)}
            startLng={parseFloat(lng)}
            itinerary={itinerary}
            picking={picking}
            nudge={nudge}
            onPickStart={handlePickStart}
            hoveredStopId={hoveredStopId}
            onHoverStop={setHoveredStopId}
          />
        </div>
        <section className="results" aria-busy={loading}>
          <p className="sr-only" role="status">
            {announcement}
          </p>
          {loading ? (
            <LoadingPanel />
          ) : error ? (
            <ErrorPanel detail={error} onRetry={() => runPlan(Number(timeMin), Number(moneyVnd))} />
          ) : itinerary && !hasResults ? (
            <EmptyPanel onAddTime={handleAddTime} onAddMoney={handleAddMoney} />
          ) : itinerary ? (
            <Results
              itinerary={itinerary}
              hoveredStopId={hoveredStopId}
              onHoverStop={setHoveredStopId}
              onReset={handleReset}
            />
          ) : null}
        </section>
      </main>
      {/* Mounts only with stops: a persistent empty bar would eat 44px
          of a phone screen for nothing. */}
      {hasResults && <TotalsBar itinerary={itinerary} onReset={handleReset} />}
    </>
  )
}

export default App
