// Shared display formatters — the app's one vocabulary for money and time.

// vi-VN groups thousands with dots: 250000 -> "250.000".
const VND = new Intl.NumberFormat('vi-VN')

/** Format a VND amount for display, e.g. 250000 -> "250.000 ₫". */
export function formatVnd(amount) {
  return `${VND.format(amount)} ₫`
}

/** Format minutes as a short duration, e.g. 150 -> "2h 30m", 45 -> "45m". */
export function formatDuration(minutes) {
  const h = Math.floor(minutes / 60)
  const m = Math.round(minutes % 60)
  if (h === 0) return `${m}m`
  if (m === 0) return `${h}h`
  return `${h}h ${m}m`
}

/** Spoken-form duration for screen-reader announcements: "2 hours 30 minutes". */
export function formatDurationLong(minutes) {
  const h = Math.floor(minutes / 60)
  const m = Math.round(minutes % 60)
  const hours = h > 0 ? `${h} ${h === 1 ? 'hour' : 'hours'}` : ''
  const mins = m > 0 ? `${m} ${m === 1 ? 'minute' : 'minutes'}` : ''
  return [hours, mins].filter(Boolean).join(' ') || '0 minutes'
}

/** Spoken-form VND for announcements: "240.000 đồng" (₫ reads poorly aloud). */
export function formatVndSpoken(amount) {
  return `${VND.format(amount)} đồng`
}
