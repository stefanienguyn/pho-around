import { useState } from 'react'
import './App.css'

// Demo defaults: the District 1 start and budgets from the API smoke test,
// so the first click reproduces the documented 8-stop itinerary.
// Raw lat/lng inputs stand in for "start location" until geocoding arrives.
const DEFAULT_LAT = '10.7797'
const DEFAULT_LNG = '106.6990'
const DEFAULT_TIME_MIN = '240'
const DEFAULT_MONEY_VND = '400000'

const API_URL = 'http://127.0.0.1:8000/api/itinerary'

function App() {
  // Inputs always yield strings; keep state as strings and convert to
  // numbers only when building the API payload (the boundary).
  const [lat, setLat] = useState(DEFAULT_LAT)
  const [lng, setLng] = useState(DEFAULT_LNG)
  const [timeMin, setTimeMin] = useState(DEFAULT_TIME_MIN)
  const [moneyVnd, setMoneyVnd] = useState(DEFAULT_MONEY_VND)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(event) {
    event.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          start: { lat: Number(lat), lng: Number(lng) },
          time_budget_min: Number(timeMin),
          money_budget_vnd: Number(moneyVnd),
        }),
      })
      // fetch only rejects when no response happened at all (network, CORS);
      // an HTTP error status resolves normally and must be checked here.
      if (!res.ok) {
        throw new Error(`API error ${res.status}`)
      }
      const data = await res.json()
      console.log('itinerary:', data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main>
      <h1>Phở around</h1>
      <p>Where should we go? Tell me where you are, your time, and your budget.</p>
      <form onSubmit={handleSubmit}>
        <div className="start-fields">
          <label>
            Start latitude
            <input
              type="number"
              step="any"
              required
              value={lat}
              onChange={(e) => setLat(e.target.value)}
            />
          </label>
          <label>
            Start longitude
            <input
              type="number"
              step="any"
              required
              value={lng}
              onChange={(e) => setLng(e.target.value)}
            />
          </label>
        </div>
        <label>
          Time budget (minutes)
          <input
            type="number"
            min="1"
            required
            value={timeMin}
            onChange={(e) => setTimeMin(e.target.value)}
          />
        </label>
        <label>
          Money budget (VND)
          <input
            type="number"
            min="0"
            step="1000"
            required
            value={moneyVnd}
            onChange={(e) => setMoneyVnd(e.target.value)}
          />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? 'Planning…' : 'Plan my route'}
        </button>
      </form>
      {error && <p className="error">Could not plan a route: {error}</p>}
    </main>
  )
}

export default App
