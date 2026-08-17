import { useRef } from 'react'

// One budget control: preset chips + a slider + a formatted readout.
// Time and Money are the same interaction with different numbers, so they
// share this component and differ only by props.
//
// Chips and slider stay in sync through the single `value` in the parent:
// tapping a chip snaps the slider to it; dragging the slider away from
// every preset deselects the chips (the "Custom" chip, when present,
// lights up instead).
function BudgetControl({
  label,
  value,
  onChange,
  min,
  max,
  step,
  presets,
  formatValue,
  customChip = false,
  sliderLabel,
}) {
  const sliderRef = useRef(null)
  const n = Number(value)
  const isPreset = presets.some((preset) => preset.value === n)
  // Percent of the track to paint red (the CSS gradient reads --fill).
  const fill = `${Math.min(100, Math.max(0, ((n - min) / (max - min)) * 100))}%`

  return (
    <div className="control">
      <div className="control-label">{label}</div>
      <div className="chips" role="group" aria-label={`${label} presets`}>
        {presets.map((preset) => (
          <button
            key={preset.value}
            type="button"
            className="chip"
            aria-pressed={preset.value === n}
            onClick={() => onChange(String(preset.value))}
          >
            {preset.label}
          </button>
        ))}
        {customChip && (
          <button
            type="button"
            className="chip"
            aria-pressed={!isPreset}
            onClick={() => sliderRef.current.focus()}
          >
            Custom
          </button>
        )}
      </div>
      <div className="slider-row">
        <input
          ref={sliderRef}
          className="slider"
          type="range"
          min={min}
          max={max}
          step={step}
          value={n}
          onChange={(e) => onChange(e.target.value)}
          aria-label={sliderLabel}
          style={{ '--fill': fill }}
        />
        <output className="readout">{formatValue(n)}</output>
      </div>
    </div>
  )
}

export default BudgetControl
