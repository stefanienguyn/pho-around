import { describeConstraint } from './format'

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
  function handleSubmit(event) {
    event.preventDefault()
    if (value.trim() && !asking) {
      onSubmit(value.trim())
    }
  }

  return (
    <div className="ask">
      <form onSubmit={handleSubmit}>
        <label className="ask-label" htmlFor="ask-input">
          Or just say what you want
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
            disabled={asking}
          />
          <button className="ask-go" type="submit" disabled={asking || !value.trim()}>
            {asking ? '…' : 'Ask'}
          </button>
        </div>
      </form>

      {error && <p className="ask-error">{error}</p>}
      {reply && <p className="ask-reply">{reply}</p>}

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
