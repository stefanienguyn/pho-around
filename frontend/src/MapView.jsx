import { useEffect, useRef, useState } from 'react'
import { importLibrary, setOptions } from '@googlemaps/js-api-loader'

// Advanced markers require a map ID; Google's documented dev placeholder.
const MAP_ID = 'DEMO_MAP_ID'
const DEFAULT_ZOOM = 14
const START_PIN_COLOR = '#1a73e8'
const ROUTE_LINE = { strokeColor: '#c0392b', strokeOpacity: 0.8, strokeWeight: 3 }
const FIT_PADDING_PX = 48

const API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY

// Configure the SDK once for the whole app: Google's <script> tag is injected
// on the first importLibrary() call and cached — asking again is free.
setOptions({ key: API_KEY, v: 'weekly' })

// The Google Map: start pin, numbered stop pins, and the route line.
// React owns everything on the page except the one div this component
// renders — Google Maps owns the inside of that div.
function MapView({ startLat, startLng, itinerary, onPickStart }) {
  const mapDivRef = useRef(null) // the DOM node handed to Google
  const mapRef = useRef(null) // the google.maps.Map instance
  const overlaysRef = useRef([]) // markers + polyline currently drawn
  const [mapReady, setMapReady] = useState(false)

  function clearOverlays() {
    for (const overlay of overlaysRef.current) {
      // Polyline detaches via setMap(null); AdvancedMarkerElement via .map = null.
      if (overlay.setMap) overlay.setMap(null)
      else overlay.map = null
    }
    overlaysRef.current = []
  }

  // Effect #1 — create the map, once. Deliberately empty deps: the map is
  // built with the initial start and updated imperatively afterwards;
  // re-running this would rebuild the whole map on every keystroke.
  useEffect(() => {
    if (!API_KEY) return undefined
    let cancelled = false
    async function createMap() {
      const { Map } = await importLibrary('maps')
      // StrictMode runs mount → unmount → mount in dev; the flag stops the
      // first, already-cleaned-up run from building a second map in this div.
      if (cancelled) return
      const map = new Map(mapDivRef.current, {
        center: { lat: startLat, lng: startLng },
        zoom: DEFAULT_ZOOM,
        mapId: MAP_ID,
      })
      // Click anywhere → that point becomes the new start. Safe to capture
      // once: the handler only calls React state setters, which never change.
      map.addListener('click', (event) => {
        onPickStart(event.latLng.lat(), event.latLng.lng())
      })
      mapRef.current = map
      setMapReady(true)
    }
    createMap()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Effect #2 — (re)draw overlays whenever the start or the itinerary
  // changes. Cleanup erases the previous drawing first, so stale markers
  // never linger after a re-plan.
  useEffect(() => {
    // Not ready, or a start field is mid-edit (parseFloat('') → NaN): draw nothing.
    if (!mapReady || !Number.isFinite(startLat) || !Number.isFinite(startLng)) return undefined
    let cancelled = false
    async function draw() {
      const [{ AdvancedMarkerElement, PinElement }, { Polyline }, { LatLngBounds }] =
        await Promise.all([
          importLibrary('marker'),
          importLibrary('maps'),
          importLibrary('core'),
        ])
      if (cancelled) return
      const map = mapRef.current
      clearOverlays()

      const start = { lat: startLat, lng: startLng }
      const startPin = new PinElement({
        glyph: 'S',
        background: START_PIN_COLOR,
        borderColor: START_PIN_COLOR,
        glyphColor: 'white',
      })
      overlaysRef.current.push(
        new AdvancedMarkerElement({ map, position: start, content: startPin.element, title: 'Start' })
      )
      if (!itinerary || itinerary.stops.length === 0) return

      const path = [start]
      itinerary.stops.forEach((stop, index) => {
        const position = { lat: stop.place.lat, lng: stop.place.lng }
        const pin = new PinElement({ glyph: String(index + 1), glyphColor: 'white' })
        overlaysRef.current.push(
          new AdvancedMarkerElement({ map, position, content: pin.element, title: stop.place.name })
        )
        path.push(position)
      })
      overlaysRef.current.push(new Polyline({ map, path, ...ROUTE_LINE }))

      // Zoom/pan so the whole route is visible.
      const bounds = new LatLngBounds()
      for (const point of path) bounds.extend(point)
      map.fitBounds(bounds, FIT_PADDING_PX)
    }
    draw()
    return () => {
      cancelled = true
      clearOverlays()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapReady, startLat, startLng, itinerary])

  if (!API_KEY) {
    return <p className="error">Map disabled: VITE_GOOGLE_MAPS_API_KEY is not set (see .env.example).</p>
  }
  return <div className="map" ref={mapDivRef} />
}

export default MapView
