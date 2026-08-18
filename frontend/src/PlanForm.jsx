import BudgetControl from './BudgetControl'
import { formatDuration, formatVnd } from './format'

const TIME_PRESETS = [
  { label: '1h', value: 60 },
  { label: '2h', value: 120 },
  { label: '3h', value: 180 },
  { label: '4h', value: 240 },
]

const MONEY_PRESETS = [
  { label: '100k', value: 100000 },
  { label: '200k', value: 200000 },
  { label: '500k', value: 500000 },
  { label: '1tr', value: 1000000 },
]

// The plan form. All state lives in App (the map needs the same start
// coords); this component only renders it and reports edits upward.
function PlanForm({
  lat,
  lng,
  onLatChange,
  onLngChange,
  timeMin,
  onTimeChange,
  moneyVnd,
  onMoneyChange,
  picking,
  onMove,
  locating,
  geoNote,
  onUseLocation,
  loading,
  onSubmit,
}) {
  const hasStart = Number.isFinite(parseFloat(lat)) && Number.isFinite(parseFloat(lng))

  return (
    <form onSubmit={onSubmit}>
      <div className="control">
        <div className="control-label">Start</div>
        <div className="start-row">
          {hasStart ? (
            <>
              {/* Mirrors the cobalt start pin on the map. */}
              <span className="start-dot" aria-hidden="true" />
              <span className="start-value">
                {parseFloat(lat).toFixed(5)}, {parseFloat(lng).toFixed(5)}
              </span>
              {!picking && (
                <button type="button" className="text-button" onClick={onMove}>
                  Move
                </button>
              )}
            </>
          ) : (
            <span className="start-empty">Tap the map to set your start</span>
          )}
          {/* Rendered in both start states: locate for the first time, or
              re-locate after moving around. */}
          <button
            type="button"
            className="text-button"
            onClick={onUseLocation}
            disabled={locating}
          >
            {locating ? 'Locating…' : 'Use my location'}
          </button>
        </div>
        {geoNote && <p className="geo-note">{geoNote}</p>}
        <details className="coords">
          <summary>Enter coordinates instead</summary>
          <div className="start-fields">
            <label>
              Latitude
              <input
                type="number"
                name="lat"
                step="any"
                value={lat}
                onChange={(e) => onLatChange(e.target.value)}
              />
            </label>
            <label>
              Longitude
              <input
                type="number"
                name="lng"
                step="any"
                value={lng}
                onChange={(e) => onLngChange(e.target.value)}
              />
            </label>
          </div>
        </details>
      </div>

      <BudgetControl
        label="Time"
        value={timeMin}
        onChange={onTimeChange}
        min={30}
        max={360}
        step={15}
        presets={TIME_PRESETS}
        formatValue={formatDuration}
        customChip
        sliderLabel="Time in minutes"
      />

      <BudgetControl
        label="Money"
        value={moneyVnd}
        onChange={onMoneyChange}
        min={50000}
        max={2000000}
        step={25000}
        presets={MONEY_PRESETS}
        formatValue={formatVnd}
        sliderLabel="Money in đồng"
      />

      <button type="submit" className="plan-button" disabled={loading}>
        {loading ? 'Planning…' : 'Plan my afternoon'}
      </button>
    </form>
  )
}

export default PlanForm
