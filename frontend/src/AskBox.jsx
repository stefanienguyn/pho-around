import { describeConstraint } from './format'
import { preloadPlaces } from './places'

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
  function submit() {
    if (value.trim() && !asking) {
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
      <label className="ask-label" htmlFor="ask-input">
        What are you in the mood for?
      </label>
      <div className="ask-row">
        <input
          id="ask-input"
          className="ask-input"
          type="text"
          value={value}
          maxLength={500}
          placeholder="cà phê, không shopping, tối đa 3 chỗ"
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
          {asking ? '…' : 'Ask'}
        </button>
      </div>

      {/* The model takes a few seconds (more on a cold backend); a line of
          text is the honest signal — a "…" in a button reads as nothing. */}
      {asking && (
        <p className="ask-reply" role="status">
          Reading that…
        </p>
      )}
      {error && <p className="ask-error">{error}</p>}
      {reply && !asking && <p className="ask-reply">{reply}</p>}

      {constraints.length > 0 && (
        <>
          <ul className="ask-chips">
            {constraints.map((constraint, index) => (
              <li className="ask-chip" key={`${constraint.type}-${index}`}>
                {describeConstraint(constraint)}
              </li>
            ))}
          </ul>
          <button className="ask-clear" type="button" onClick={onClear}>
            Clear
          </button>
        </>
      )}
      {dropped > 0 && (
        <p className="ask-error">
          {dropped === 1 ? "One thing wasn't understood" : `${dropped} things weren't understood`}
        </p>
      )}
      <p className="ask-note">Interpreted by Google Gemini</p>
    </div>
  )
}

export default AskBox
