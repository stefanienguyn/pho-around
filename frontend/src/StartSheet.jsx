import PlaceSearch from './PlaceSearch'

/**
 * "Where are you starting from?" — asked only after a sentence has been
 * understood and there is no start point yet. Three answers: the device's
 * location, a place name, or the map (which closes the sheet and hands over
 * to the map's own tap-to-set hint). Picking any of them plans immediately.
 */
function StartSheet({ locating, geoNote, onUseLocation, onPickPlace, onUseMap, onDismiss }) {
  return (
    <div className="sheet-backdrop">
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
