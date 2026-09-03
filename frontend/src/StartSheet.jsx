import { useEffect } from 'react'
import PlaceSearch from './PlaceSearch'

/**
 * "Where are you starting from?" — asked only after a sentence has been
 * understood and there is no start point yet. Three answers: the device's
 * location, a place name, or the map (which closes the sheet and hands over
 * to the map's own tap-to-set hint). Picking any of them plans immediately.
 */
function StartSheet({ title, locating, geoNote, onUseLocation, onPickPlace, onUseMap, onDismiss }) {
  // The card is NOT position:fixed — that was two bugs in a row. The phone
  // keyboard scrolls the page to chase the text caret, and iOS repositions
  // fixed overlays against the layout viewport, so a fixed card either got
  // shoved off-screen or drifted while typing. In normal document flow near
  // the top of the page, iOS's own caret-scrolling moves the card and the
  // suggestion dropdown as one piece: the input holds its spot and the
  // suggestions unfold beneath it. The only script left is scrolling the
  // page to the top on open so the card is where the eye already is.
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [])

  return (
    <>
      <div className="sheet-backdrop" onClick={onDismiss} aria-hidden="true" />
      <div className="sheet" role="dialog" aria-modal="true" aria-labelledby="sheet-title">
        <h2 id="sheet-title" className="sheet-title">
          {title}
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
    </>
  )
}

export default StartSheet
