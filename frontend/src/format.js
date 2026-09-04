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

/** Spoken-form duration for screen-reader announcements: "2 hours 30 minutes"
 * (vi: "2 giờ 30 phút"). `lang` is 'en' or 'vi'. */
export function formatDurationLong(minutes, lang = 'en') {
  const h = Math.floor(minutes / 60)
  const m = Math.round(minutes % 60)
  if (lang === 'vi') {
    const hours = h > 0 ? `${h} giờ` : ''
    const mins = m > 0 ? `${m} phút` : ''
    return [hours, mins].filter(Boolean).join(' ') || '0 phút'
  }
  const hours = h > 0 ? `${h} ${h === 1 ? 'hour' : 'hours'}` : ''
  const mins = m > 0 ? `${m} ${m === 1 ? 'minute' : 'minutes'}` : ''
  return [hours, mins].filter(Boolean).join(' ') || '0 minutes'
}

/** Spoken-form VND for announcements: "240.000 đồng" (₫ reads poorly aloud). */
export function formatVndSpoken(amount) {
  return `${VND.format(amount)} đồng`
}

// Human-readable labels for the six place categories, so a constraint can be
// shown back to the person in words rather than as the API's vocabulary.
const CATEGORY_LABELS = {
  en: {
    landmark: 'landmark',
    coffee: 'coffee',
    food: 'food',
    dessert: 'dessert',
    shopping: 'shopping',
    photobooth: 'photobooth',
  },
  vi: {
    landmark: 'địa danh',
    coffee: 'cà phê',
    food: 'đồ ăn',
    dessert: 'tráng miệng',
    shopping: 'mua sắm',
    photobooth: 'photobooth',
  },
}

/**
 * Describe one constraint in plain words. `lang` is 'en' or 'vi'.
 *
 * Showing these back is the only defence against the model reading a sentence
 * correctly in form but backwards in meaning — "no coffee" becoming "at least
 * 1 coffee" passes every validator we have, and is obvious to a human in half
 * a second. So the words matter more than they look.
 */
export function describeConstraint(constraint, lang = 'en') {
  const category = CATEGORY_LABELS[lang][constraint.category] ?? constraint.category
  const vi = lang === 'vi'
  switch (constraint.type) {
    case 'min_category':
      return vi ? `ít nhất ${constraint.count} ${category}` : `at least ${constraint.count} ${category}`
    case 'max_category':
      return vi ? `tối đa ${constraint.count} ${category}` : `at most ${constraint.count} ${category}`
    case 'exclude_category':
      return vi ? `không ${category}` : `no ${category}`
    case 'boost_category':
      if (vi) return constraint.factor >= 1 ? `ưu tiên ${category}` : `bớt ${category}`
      return constraint.factor >= 1 ? `prefer ${category}` : `less ${category}`
    case 'require_place':
      return vi ? `phải có ${constraint.id}` : `must include ${constraint.id}`
    case 'exclude_place':
      return vi ? `bỏ qua ${constraint.id}` : `skip ${constraint.id}`
    case 'max_stops':
      return vi ? `tối đa ${constraint.count} chỗ` : `max ${constraint.count} stops`
    case 'first_place':
      return vi ? `bắt đầu với ${constraint.id}` : `start with ${constraint.id}`
    case 'first_category':
      return vi ? `${category} trước` : `${category} first`
    default:
      return constraint.type
  }
}
