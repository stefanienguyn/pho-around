import { useEffect, useRef } from 'react'
import { importLibrary } from '@googlemaps/js-api-loader'
import { CITY_CENTER, CITY_RADIUS_M } from './city'

/**
 * A place-name search that resolves to coordinates.
 *
 * Google's PlaceAutocompleteElement is a web component: it draws its own
 * input and dropdown, and React does not own what happens inside it. So this
 * component only provides a mount point (the ref) and wires one DOM event —
 * `gmp-select` — back into React through `onPick(lat, lng)`.
 *
 * Billing shape: every keystroke burst is an Autocomplete request; the one
 * fetchFields call asks for `location` only, which is the cheapest
 * (Essentials) Place Details tier.
 */
function PlaceSearch({ onPick }) {
  const mountRef = useRef(null)
  // The latest onPick, so the once-registered listener never goes stale.
  const onPickRef = useRef(onPick)
  onPickRef.current = onPick

  useEffect(() => {
    let cancelled = false
    let element = null

    async function mount() {
      // Same loader as the map: the SDK script is already on the page, this
      // just pulls in the `places` library.
      const { PlaceAutocompleteElement } = await importLibrary('places')
      if (cancelled || !mountRef.current) return
      element = new PlaceAutocompleteElement({
        // Suggestions lean toward the city; nothing outside Việt Nam at all.
        locationBias: { center: CITY_CENTER, radius: CITY_RADIUS_M },
        includedRegionCodes: ['vn'],
      })
      // The component follows the OS theme by default; the sheet is a paper
      // card whatever the OS says. (Attribute form — the property alone is
      // ignored before the element is attached.)
      element.setAttribute('color-scheme', 'LIGHT')
      element.addEventListener('gmp-select', async (event) => {
        const place = event.placePrediction.toPlace()
        await place.fetchFields({ fields: ['location'] })
        onPickRef.current(place.location.lat(), place.location.lng())
      })
      mountRef.current.replaceChildren(element)
      element.focus()
    }

    mount()
    return () => {
      cancelled = true
      element?.remove()
    }
  }, [])

  return <div className="place-search" ref={mountRef} />
}

export default PlaceSearch
