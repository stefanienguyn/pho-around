import { useRef, useState } from 'react'
import { importLibrary } from '@googlemaps/js-api-loader'
import { CITY_CENTER, CITY_RADIUS_M } from './city'

// One Places session = the keystrokes + the final details call, billed as a
// unit. The token resets after each pick so the next search is its own session.
const DEBOUNCE_MS = 250

/**
 * A place-name search that resolves to coordinates.
 *
 * Our own input + suggestion list over Google's *data* API
 * (`AutocompleteSuggestion`), not the `PlaceAutocompleteElement` widget: on
 * narrow screens that widget takes over the whole viewport with its own
 * fullscreen search UI — the card, the page, everything vanishes behind it.
 * Drawing the list ourselves keeps the suggestions inside the card, unfolding
 * under the input, styled by our tokens.
 *
 * Expects `onPick(lat, lng)`; calls it once when a suggestion is chosen.
 */
function PlaceSearch({ onPick }) {
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const sessionRef = useRef(null) // AutocompleteSessionToken, one per search
  const timerRef = useRef(0)
  const latestRef = useRef('') // drop answers that arrive out of order

  async function fetchSuggestions(text) {
    const { AutocompleteSuggestion, AutocompleteSessionToken } = await importLibrary('places')
    if (!sessionRef.current) {
      sessionRef.current = new AutocompleteSessionToken()
    }
    try {
      const { suggestions: found } = await AutocompleteSuggestion.fetchAutocompleteSuggestions({
        input: text,
        sessionToken: sessionRef.current,
        locationBias: { center: CITY_CENTER, radius: CITY_RADIUS_M },
        includedRegionCodes: ['vn'],
      })
      if (latestRef.current === text) {
        setSuggestions(found)
      }
    } catch {
      // Quota spent or network gone: no suggestions is a quiet, honest state —
      // the sheet's other two paths (location, map) still work.
      if (latestRef.current === text) {
        setSuggestions([])
      }
    }
  }

  function handleChange(event) {
    const text = event.target.value
    setQuery(text)
    latestRef.current = text
    clearTimeout(timerRef.current)
    if (!text.trim()) {
      setSuggestions([])
      return
    }
    timerRef.current = setTimeout(() => fetchSuggestions(text.trim()), DEBOUNCE_MS)
  }

  // Enter = take the top suggestion; the list is tappable for the rest.
  function handleKeyDown(event) {
    if (event.key === 'Enter') {
      event.preventDefault()
      if (suggestions.length > 0) {
        pick(suggestions[0])
      }
    }
  }

  async function pick(suggestion) {
    const place = suggestion.placePrediction.toPlace()
    // Location only — the cheapest (Essentials) details tier, and it ends
    // the billing session.
    await place.fetchFields({ fields: ['location'] })
    sessionRef.current = null
    setSuggestions([])
    setQuery('')
    onPick(place.location.lat(), place.location.lng())
  }

  return (
    <div className="place-search">
      <input
        id="place-search"
        type="text"
        className="place-input"
        value={query}
        placeholder="Bến Thành, Thảo Điền, 42 Nguyễn Huệ…"
        autoComplete="off"
        onChange={handleChange}
        onKeyDown={handleKeyDown}
      />
      {suggestions.length > 0 && (
        <ul className="place-list">
          {suggestions.map((suggestion) => {
            const prediction = suggestion.placePrediction
            return (
              <li key={prediction.placeId}>
                <button type="button" className="place-option" onClick={() => pick(suggestion)}>
                  <span className="place-main">{prediction.mainText?.text ?? prediction.text.text}</span>
                  {prediction.secondaryText && (
                    <span className="place-secondary">{prediction.secondaryText.text}</span>
                  )}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

export default PlaceSearch
