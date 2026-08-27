import { importLibrary } from '@googlemaps/js-api-loader'

/**
 * Warm the `places` library ahead of need. The SDK downloads each library on
 * first importLibrary() and caches it, so calling this when the ask box gets
 * focus means the start sheet's search input appears with no download in the
 * way. Fire-and-forget: PlaceSearch awaits the same cached promise.
 */
export function preloadPlaces() {
  importLibrary('places').catch(() => {})
}
