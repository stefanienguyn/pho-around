import { useEffect, useRef, useState } from 'react'
import { importLibrary, setOptions } from '@googlemaps/js-api-loader'
import { CITY_CENTER } from './city'

// Points at the "pho-around-web" cloud map config (Vector + the
// "Plastic Stool paper" style; styling lives in the console, and inline
// `styles` options are ignored once a map ID is set). Not a secret —
// it names a look; the API key does the authenticating. Advanced
// markers require some map ID either way.
const MAP_ID = '52428a84057d1b9f56ca9c30'
const DEFAULT_ZOOM = 14
// Stop pins sit above the start pin; the hovered pin above everything.
const Z_START_PIN = 1
const Z_STOP_PIN = 10
const Z_HOVERED_PIN = 100
// Mirrors the App.css --red token: the Polyline API takes JS values, so
// this can't read CSS variables — keep in sync by hand. Full opacity and
// 4px per the brief: this is a real route, not an estimate.
const ROUTE_LINE = { strokeColor: '#E23D33', strokeOpacity: 1, strokeWeight: 4 }
const FIT_PADDING_PX = 48

const API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY

// Build a pin as a real DOM node for AdvancedMarkerElement: it inherits
// App.css, so map pins and card numbers are literally the same drawn
// object (the .disc), never two drifting imitations.
function makeDisc(...classNames) {
  const disc = document.createElement('div')
  disc.classList.add('disc', 'map-pin', ...classNames)
  return disc
}

// Configure the SDK once for the whole app: Google's <script> tag is injected
// on the first importLibrary() call and cached — asking again is free.
setOptions({ key: API_KEY, v: 'weekly' })

// The Google Map: start pin, numbered stop pins, and the route line.
// React owns everything on the page except the one div this component
// renders — Google Maps owns the inside of that div.
function MapView({
  startLat,
  startLng,
  itinerary,
  picking,
  onPickStart,
  hoveredStopId,
  onHoverStop,
}) {
  const mapDivRef = useRef(null) // the DOM node handed to Google
  const mapRef = useRef(null) // the google.maps.Map instance
  const overlaysRef = useRef([]) // markers + polyline currently drawn
  const stopMarkersRef = useRef(new Map()) // place id → its stop marker
  const shellRef = useRef(null) // our wrapper (hint pill)
  // The click listener is captured once at map creation, so it would see
  // the first render's `picking` forever; a ref always holds the latest.
  const pickingRef = useRef(picking)
  const [mapReady, setMapReady] = useState(false)

  function clearOverlays() {
    for (const overlay of overlaysRef.current) {
      // Polyline detaches via setMap(null); AdvancedMarkerElement via .map = null.
      if (overlay.setMap) overlay.setMap(null)
      else overlay.map = null
    }
    overlaysRef.current = []
    stopMarkersRef.current.clear()
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
        center: Number.isFinite(startLat) ? { lat: startLat, lng: startLng } : CITY_CENTER,
        zoom: DEFAULT_ZOOM,
        mapId: MAP_ID,
        // POI icons must not swallow clicks: tapping one would open
        // Google's info window instead of cleanly setting the start.
        clickableIcons: false,
      })
      // Click → new start, but only while in picking mode (read through
      // the ref: this closure is captured once and would go stale).
      map.addListener('click', (event) => {
        if (!pickingRef.current) return
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

  // Keep the click listener's ref current and show the picking cursor:
  // a crosshair says "the map is listening for your start point".
  useEffect(() => {
    pickingRef.current = picking
    if (mapReady) {
      mapRef.current.setOptions({ draggableCursor: picking ? 'crosshair' : null })
    }
  }, [picking, mapReady])

  // The card ↔ pin link, map side: the hovered stop's pin scales up and
  // rises above its neighbours.
  useEffect(() => {
    for (const [id, marker] of stopMarkersRef.current) {
      const hot = id === hoveredStopId
      marker.content.classList.toggle('is-hot', hot)
      marker.zIndex = hot ? Z_HOVERED_PIN : Z_STOP_PIN
    }
  }, [hoveredStopId, itinerary])

  // Effect #2 — (re)draw overlays whenever the start or the itinerary
  // changes. Cleanup erases the previous drawing first, so stale markers
  // never linger after a re-plan.
  useEffect(() => {
    // Not ready, or a start field is mid-edit (parseFloat('') → NaN): draw nothing.
    if (!mapReady || !Number.isFinite(startLat) || !Number.isFinite(startLng)) return undefined
    let cancelled = false
    async function draw() {
      const [{ AdvancedMarkerElement }, { Polyline }, { LatLngBounds }] = await Promise.all([
        importLibrary('marker'),
        importLibrary('maps'),
        importLibrary('core'),
      ])
      if (cancelled) return
      const map = mapRef.current
      clearOverlays()

      const start = { lat: startLat, lng: startLng }
      overlaysRef.current.push(
        new AdvancedMarkerElement({
          map,
          position: start,
          content: makeDisc('start-pin'),
          title: 'Start',
          zIndex: Z_START_PIN,
        })
      )
      if (!itinerary || itinerary.stops.length === 0) return

      const path = [start]
      itinerary.stops.forEach((stop, index) => {
        const position = { lat: stop.place.lat, lng: stop.place.lng }
        const disc = makeDisc('stop-pin')
        disc.textContent = String(index + 1)
        disc.addEventListener('mouseenter', () => onHoverStop(stop.place.id))
        disc.addEventListener('mouseleave', () => onHoverStop(null))
        const marker = new AdvancedMarkerElement({
          map,
          position,
          content: disc,
          title: stop.place.name,
          zIndex: Z_STOP_PIN,
        })
        stopMarkersRef.current.set(stop.place.id, marker)
        overlaysRef.current.push(marker)
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
  // The shell is ours (hint pill, focus target); Google owns only the
  // inside of the .map div, exactly as before.
  return (
    <div className="map-shell" ref={shellRef}>
      <div className="map" ref={mapDivRef} />
      {picking && (
        <p className="map-hint">Tap the map to set your start</p>
      )}
    </div>
  )
}

export default MapView
