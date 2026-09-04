import { useRef, useState } from 'react'
import { useT } from './i18n'

// One budget control: preset chips + a slider + a formatted readout.
// Time and Money are the same interaction with different numbers, so they
// share this component and differ only by props.
//
// Chips and slider stay in sync through the single `value` in the parent:
// tapping a chip snaps the slider to it; dragging the slider away from
// every preset deselects the chips and lights up "Custom" instead.
//
// "Custom" opens a typed input. A slider is good at roughly and bad at
// exactly — "2.5 hours" or "350.000 ₫" is a drag-and-squint on a track and
// two keystrokes in a field.
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
  // The unit the typed field works in, which is not always the unit stored:
  // time is held in minutes but people think in hours, so factor converts.
  customUnit = '',
  customFactor = 1,
  sliderLabel,
}) {
  const t = useT()
  const customRef = useRef(null)
  const [customOpen, setCustomOpen] = useState(false)
  const n = Number(value)
  const isPreset = presets.some((preset) => preset.value === n)
  // Percent of the track to paint red (the CSS gradient reads --fill).
  const fill = `${Math.min(100, Math.max(0, ((n - min) / (max - min)) * 100))}%`

  function openCustom() {
    setCustomOpen((open) => !open)
    // Focus after the input exists. Without the frame the ref is still null.
    requestAnimationFrame(() => customRef.current?.focus())
  }

  function handleCustomInput(raw) {
    if (raw === '') {
      return // let the field empty out while typing; don't snap to min
    }
    const typed = Number(raw) * customFactor
    if (Number.isNaN(typed)) {
      return
    }
    // Clamp rather than reject: the slider's range is the real limit, and
    // silently ignoring a typed number reads as the field being broken.
    onChange(String(Math.min(max, Math.max(min, Math.round(typed)))))
  }

  return (
    <div className="control">
      <div className="control-label">{label}</div>
      <div className="chips" role="group" aria-label={`${label} ${t.presetsSuffix}`}>
        {presets.map((preset) => (
          <button
            key={preset.value}
            type="button"
            className="chip"
            aria-pressed={preset.value === n}
            onClick={() => {
              setCustomOpen(false)
              onChange(String(preset.value))
            }}
          >
            {preset.label}
          </button>
        ))}
        {customChip && (
          <button
            type="button"
            className="chip"
            aria-pressed={customOpen || !isPreset}
            aria-expanded={customOpen}
            onClick={openCustom}
          >
            {t.custom}
          </button>
        )}
      </div>
      {customOpen && (
        <label className="custom-field">
          <input
            ref={customRef}
            type="number"
            inputMode="decimal"
            min={min / customFactor}
            max={max / customFactor}
            step={step / customFactor}
            value={n / customFactor}
            onChange={(e) => handleCustomInput(e.target.value)}
          />
          <span>{customUnit}</span>
        </label>
      )}
      <div className="slider-row">
        <input
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
