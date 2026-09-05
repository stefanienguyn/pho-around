import { createPortal } from 'react-dom'
import { describeConstraint } from './format'
import { useLang, useT } from './i18n'
import { preloadPlaces } from './places'

// Example sentence, not chrome: place-flavoured Vietnamese in both languages.
const ASK_PLACEHOLDER = 'cà phê, không shopping, tối đa 3 chỗ'

/**
 * A sentence in, planning constraints out.
 *
 * Presentational only — App owns the fetch, matching PlanForm. Whatever the
 * model understood is shown back as chips *before* the route appears, because
 * a misread request is invisible in a plan but obvious in a list.
 *
 * Provisional styling: this is the demo version, restyled in the UI redesign.
 */
function AskBox({ value, onChange, onSubmit, asking, reply, constraints, dropped, error, onClear }) {
  const { lang } = useLang()
  const t = useT()
  function submit() {
    if (value.trim() && !asking) {
      // Drop focus so the phone keyboard closes — pressing the keyboard's
      // return key would otherwise leave it up over "Reading that…".
      document.activeElement?.blur()
      onSubmit(value.trim())
    }
  }

  // No <form> element here on purpose: this box renders INSIDE PlanForm's
  // form, and nested forms are invalid HTML — browsers drop the inner one,
  // so Enter and the button would fall through and submit the *plan*.
  // Enter is handled on the input instead, and the button is type="button"
  // (a bare <button> inside a form defaults to submit).
  function handleKeyDown(event) {
    if (event.key === 'Enter') {
      event.preventDefault()
      submit()
    }
  }

  return (
    <div className="ask">
      {/* The visible label is optional (currently off in i18n.js); the
          aria-label keeps the input named for screen readers either way. */}
      {t.askLabel && (
        <label className="ask-label" htmlFor="ask-input">
          {t.askLabel}
        </label>
      )}
      <div className="ask-row">
        <input
          id="ask-input"
          className="ask-input"
          type="text"
          value={value}
          maxLength={500}
          placeholder={ASK_PLACEHOLDER}
          aria-label={t.askLabel ? undefined : ASK_PLACEHOLDER}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={preloadPlaces}
          disabled={asking}
        />
        <button
          className="ask-go"
          type="button"
          onClick={submit}
          disabled={asking || !value.trim()}
        >
          {asking ? '…' : t.askButton}
        </button>
      </div>

      {/* The model takes a few seconds (more on a cold backend). A centered
          overlay carries the wait: the bowl logo spinning over a scrim, with
          one honest line. role="status" announces it once. */}
      {/* Portal: the hero's entrance animations leave transforms on every
          child (fill: both), each a stacking context that would trap and
          overpaint a fixed overlay. Rendering at document.body escapes. */}
      {asking &&
        createPortal(
          <div className="ask-overlay" role="status">
            <div className="ask-overlay-card">
              <img className="bowl-spinner" src="/favicon.png" alt="" />
              <p className="ask-overlay-text">{t.askReading}</p>
            </div>
          </div>,
          document.body
        )}
      {error && <p className="ask-error">{error}</p>}
      {reply && !asking && <p className="ask-reply">{reply}</p>}

      {constraints.length > 0 && (
        <>
          <ul className="ask-chips">
            {constraints.map((constraint, index) => (
              <li className="ask-chip" key={`${constraint.type}-${index}`}>
                {describeConstraint(constraint, lang)}
              </li>
            ))}
          </ul>
          <button className="ask-clear" type="button" onClick={onClear}>
            {t.askClear}
          </button>
        </>
      )}
      {dropped > 0 && (
        <p className="ask-error">
          {dropped === 1 ? t.askDroppedOne : t.askDroppedMany(dropped)}
        </p>
      )}
    </div>
  )
}

export default AskBox
