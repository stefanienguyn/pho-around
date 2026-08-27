import { useEffect, useRef, useState } from 'react'

// Served straight from public/ — Vite copies that folder as-is and never
// inlines it, so the 4.9 MB video is a separate request, not bundle weight.
const VIDEO_SRC = '/hero.mp4'
const POSTER_SRC = '/hero.jpg'

/**
 * The landing hero: a looping clip of Chợ Bến Thành with one question on it.
 *
 * `collapsed` = something occupies the results region; the hero shrinks to
 * its nav row and the <video> is unmounted (a hidden video still decodes).
 * `children` is the ask box — App owns its state, exactly as with PlanForm.
 */
function Hero({ collapsed, children }) {
  const videoRef = useRef(null)
  // True once the browser refused to autoplay (iOS Low Power Mode, data
  // saver): the video comes out of the DOM and the poster — the hero's
  // background image — stands in. Otherwise Safari paints its own play
  // button over a video that is meant to be wallpaper.
  const [refused, setRefused] = useState(false)

  // Autoplay policy: browsers only autoplay video that is muted, and
  // React's `muted` prop sets the DOM *property* but not the HTML attribute
  // that Chrome checks at load — so the element is muted by hand here, and
  // play() is called explicitly so the refusal is observable.
  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    video.muted = true
    video.play().catch(() => setRefused(true))
  }, [collapsed])

  return (
    <header className={collapsed ? 'hero has-results' : 'hero'}>
      {!collapsed && !refused && (
        <video
          ref={videoRef}
          className="hero-video"
          src={VIDEO_SRC}
          poster={POSTER_SRC}
          autoPlay
          loop
          muted
          playsInline
          preload="metadata"
          aria-hidden="true"
        />
      )}
      <nav className="hero-nav">
        <span className="wordmark">Phở around</span>
        <span className="hero-pill">Early demo</span>
      </nav>
      {/* --stagger orders the entrance; the CSS multiplies it by 120ms. */}
      <div className="hero-body">
        <span className="hero-pill" style={{ '--stagger': 0 }}>
          <span className="disc" aria-hidden="true" />
          Sài Gòn · tối nay
        </span>
        <h1 className="hero-title" style={{ '--stagger': 1 }}>
          <span>Tell us what you're</span>
          <span>
            craving <em className="hero-accent">tối nay</em>
          </span>
        </h1>
        <p className="subline" style={{ '--stagger': 2 }}>
          One sentence. A route around Sài Gòn that fits your time and your money.
        </p>
        <div style={{ '--stagger': 3 }} className="ask-slot">
          {children}
        </div>
        <a className="hero-skip" href="#plan" style={{ '--stagger': 4 }}>
          or set it up by hand ↓
        </a>
        {/* Sets expectations before anything can disappoint: a first visitor
            meeting a cold start or a spent daily allowance reads it as a broken
            site unless told otherwise. Not dismissible — it is two lines, and a
            dismissed banner is the one nobody reads. */}
        <p className="demo-note" role="status" style={{ '--stagger': 5 }}>
          <strong>Early demo.</strong> Still being built, so it can be slow to wake up and asking
          in words has a small daily allowance. Thanks for your patience 🍜
        </p>
      </div>
    </header>
  )
}

export default Hero
