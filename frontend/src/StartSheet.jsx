import { useEffect, useRef } from 'react'
import PlaceSearch from './PlaceSearch'

/**
 * "Where are you starting from?" — asked only after a sentence has been
 * understood and there is no start point yet. Three answers: the device's
 * location, a place name, or the map (which closes the sheet and hands over
 * to the map's own tap-to-set hint). Picking any of them plans immediately.
 */
function StartSheet({ locating, geoNote, onUseLocation, onPickPlace, onUseMap, onDismiss }) {
  const backdropRef = useRef(null)

  // "Centered" must mean centered in what the person can SEE. The phone
  // keyboard shrinks only the *visual* viewport — CSS units (vh/svh/dvh) all
  // ignore it — so focusing the address field left the sheet centered in the
  // full page while Safari shoved the input to the top. Track the visual
  // viewport by hand and size the backdrop to it; the grid re-centers inside.
  useEffect(() => {
    const viewport = window.visualViewport
    const backdrop = backdropRef.current
    if (!viewport || !backdrop) return

    function fit() {
      backdrop.style.top = `${viewport.offsetTop}px`
      backdrop.style.height = `${viewport.height}px`
      // Keyboard open (visual viewport well below the layout viewport):
      // anchor the card to the visible TOP instead of centering. A centered
      // card re-centers every time the suggestion dropdown grows it, so the
      // input would drift while typing; top-anchored, growth is downward
      // only and the input holds still.
      const keyboardOpen = viewport.height < window.innerHeight * 0.8
      backdrop.style.placeItems = keyboardOpen ? 'start center' : ''
    }
    fit()
    viewport.addEventListener('resize', fit)
    viewport.addEventListener('scroll', fit)
    return () => {
      viewport.removeEventListener('resize', fit)
      viewport.removeEventListener('scroll', fit)
    }
  }, [])

  return (
    <div className="sheet-backdrop" ref={backdropRef}>
      <div className="sheet" role="dialog" aria-modal="true" aria-labelledby="sheet-title">
        <h2 id="sheet-title" className="sheet-title">
          Got it. Where are you starting from?
        </h2>
        <button
          type="button"
          className="sheet-button"
          onClick={onUseLocation}
          disabled={locating}
          autoFocus
        >
          {locating ? 'Locating…' : '📍 Use my location'}
        </button>
        {geoNote && <p className="geo-note">{geoNote}</p>}
        <label className="sheet-label" htmlFor="place-search">
          or search a place
        </label>
        <PlaceSearch onPick={onPickPlace} />
        <button type="button" className="text-button" onClick={onUseMap}>
          or tap the map instead
        </button>
        <button type="button" className="ask-clear sheet-dismiss" onClick={onDismiss}>
          Not now
        </button>
      </div>
    </div>
  )
}

export default StartSheet
