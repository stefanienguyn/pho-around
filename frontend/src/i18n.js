import { createContext, useContext } from 'react'

// The one language mechanism for the whole app. Both pages read and write
// the same stored key, so a choice made on either survives on the other.
// Place names, the time-of-day rotator, and money formats are content, not
// chrome — they stay identical in both languages.

// The remembered language override. Only 'en' | 'vi' are ever stored.
export const LANG_KEY = 'pho-lang'

/**
 * First-load language: an explicit earlier choice wins; otherwise the
 * browser's own language (vi-VN → Vietnamese, everything else English).
 * Returns 'en' or 'vi'.
 */
export function getInitialLang() {
  try {
    const saved = localStorage.getItem(LANG_KEY)
    if (saved === 'en' || saved === 'vi') return saved
  } catch {
    // Private mode / blocked storage: fall through to the browser language.
  }
  return navigator.language?.toLowerCase().startsWith('vi') ? 'vi' : 'en'
}

/**
 * Remember an explicit language choice. `lang` is 'en' or 'vi'.
 * Storage failures are ignored — the choice still applies for the visit.
 */
export function persistLang(lang) {
  try {
    localStorage.setItem(LANG_KEY, lang)
  } catch {
    // Same as above: no storage, no persistence, no crash.
  }
}

// Provided by each page's root component as { lang, setLang } so any
// component can read the language (or offer the toggle) without threading
// props through every layer.
export const LangContext = createContext({ lang: 'en', setLang: () => {} })

/** The { lang, setLang } pair from the nearest provider. */
export function useLang() {
  return useContext(LangContext)
}

/** The planner's string table for the current language. */
export function useT() {
  const { lang } = useContext(LangContext)
  return UI[lang]
}

// Every user-facing string in the planner, both languages, one place.
// (The About page's copy lives in About.jsx — it is page content with its
// own voice; this table is the app chrome.)
export const UI = {
  en: {
    // Hero
    heroTitle1: "What you're",
    heroTitle2: 'up to ',
    heroRotatorSr: 'tối nay',
    heroSubline: 'One sentence. A route around Sài Gòn that fits your time and your money.',
    heroSkip: 'or set it up by hand ↓',
    heroAbout: 'About us',
    heroDemo: 'Early demo',
    demoNoteStrong: 'Early demo.',
    demoNoteBody:
      ' Still being built, so it can be slow to wake up and asking in words has a small daily allowance. Thanks for your patience 🍜',
    // Ask box
    // askLabel: 'What are you in the mood for?',
    askButton: 'Ask',
    askReading: 'Making the best plan for you right now…',
    askClear: 'Clear',
    askDroppedOne: "One thing wasn't understood",
    askDroppedMany: (n) => `${n} things weren't understood`,
    askBusyFallback: 'Busy right now — try again shortly',
    askDisabled: "Asking isn't switched on here — use the sliders",
    askFailed: "Couldn't read that — try again, or use the sliders",
    // Plan form
    startLabel: 'Start',
    startEmpty: 'Tap the map to set your start',
    move: 'Move',
    useLocation: 'Use my location',
    locating: 'Locating…',
    coordsSummary: 'Enter coordinates instead',
    latitude: 'Latitude',
    longitude: 'Longitude',
    timeLabel: 'Time',
    moneyLabel: 'Money',
    custom: 'Custom',
    hoursUnit: 'hours',
    dongUnit: 'đồng',
    timeSlider: 'Time in minutes',
    moneySlider: 'Money in đồng',
    presetsSuffix: 'presets',
    planButton: 'Plan my afternoon',
    planning: 'Planning…',
    // Geolocation + start sheet (owned by App)
    geoUnavailable: 'Location isn’t available in this browser — tap the map instead.',
    geoFailed: 'Couldn’t get your location — tap the map instead.',
    sheetAfterAsk: 'Got it. Where are you starting from?',
    sheetNeedStart: 'First — where are you starting from?',
    // Start sheet
    sheetUseLocation: '📍 Use my location',
    sheetSearchLabel: 'or search a place',
    sheetUseMap: 'or tap the map instead',
    sheetDismiss: 'Not now',
    // Status panels
    loadingLabels: [
      'Checking what’s open near you',
      'Fitting your time and money',
      'Putting the stops in order',
      'Still working — the optimizer is being thorough',
    ],
    emptyTitle: 'Nothing fits — yet',
    emptyBody: 'Your budgets are a little tight for this neighbourhood.',
    addTime: '+30 minutes',
    addMoney: '+100.000 ₫',
    errorTitle: 'Couldn’t reach the planner',
    errorBody: 'Check your connection and try again.',
    retry: 'Try again',
    errorDetails: 'Technical details',
    // Results
    resultsTitle: 'Your route',
    ride: (min) => `${min} min ride`,
    stay: (min) => `stay ${min} min`,
    openInMaps: (name) => `Open ${name} in Google Maps`,
    free: 'free',
    stopWord: (n) => (n === 1 ? 'stop' : 'stops'),
    withinBudget: 'within budget',
    startOver: 'Start over',
    // Map + announcements
    mapHint: 'Tap the map to set your start',
    annPlanning: 'Planning your route',
    annError: 'Couldn’t reach the planner',
    annEmpty: 'No plan fits your budgets',
    annStops: (n) => `${n} stops`,
  },
  vi: {
    // Hero
    heroTitle1: 'Bạn muốn',
    heroTitle2: 'làm gì ',
    heroRotatorSr: 'tối nay',
    heroSubline: 'Một câu thôi. Một lịch trình vòng quanh Sài Gòn vừa thời gian, vừa túi tiền.',
    heroSkip: 'hoặc tự chỉnh bằng tay ↓',
    heroAbout: 'Về tụi mình',
    heroDemo: 'Bản demo',
    demoNoteStrong: 'Bản demo.',
    demoNoteBody:
      ' Tụi mình vẫn đang xây, nên web có lúc hơi chậm và askbox có giới hạn mỗi ngày. Cảm ơn mọi người đã kiên nhẫn 🍜',
    // Ask box
    // askLabel: 'Bạn đang thèm gì?',
    askButton: 'Hỏi',
    askReading: 'Đang lên kèo xịn nhất cho bạn nè…',
    askClear: 'Xoá',
    askDroppedOne: 'Có một ý tụi mình chưa hiểu',
    askDroppedMany: (n) => `Có ${n} ý tụi mình chưa hiểu`,
    askBusyFallback: 'Đang bận xíu — thử lại sau nhé',
    askDisabled: 'Phần hỏi chưa bật ở đây — dùng thanh kéo nhé',
    askFailed: 'Chưa đọc được câu đó — thử lại, hoặc dùng thanh kéo nhé',
    // Plan form
    startLabel: 'Điểm bắt đầu',
    startEmpty: 'Chạm bản đồ để chọn điểm bắt đầu',
    move: 'Đổi',
    useLocation: 'Dùng vị trí của tôi',
    locating: 'Đang định vị…',
    coordsSummary: 'Hoặc nhập toạ độ',
    latitude: 'Vĩ độ',
    longitude: 'Kinh độ',
    timeLabel: 'Thời gian',
    moneyLabel: 'Tiền',
    custom: 'Tuỳ chọn',
    hoursUnit: 'giờ',
    dongUnit: 'đồng',
    timeSlider: 'Thời gian tính bằng phút',
    moneySlider: 'Số tiền tính bằng đồng',
    presetsSuffix: 'mức có sẵn',
    planButton: 'Lên lịch cho tôi',
    planning: 'Đang lên lịch…',
    // Geolocation + start sheet (owned by App)
    geoUnavailable: 'Trình duyệt này không lấy được vị trí — chạm bản đồ nhé.',
    geoFailed: 'Không lấy được vị trí của bạn — chạm bản đồ nhé.',
    sheetAfterAsk: 'Nghe rồi nè. Bạn bắt đầu từ đâu?',
    sheetNeedStart: 'Trước tiên — bạn bắt đầu từ đâu?',
    // Start sheet
    sheetUseLocation: '📍 Dùng vị trí của tôi',
    sheetSearchLabel: 'hoặc tìm địa điểm',
    sheetUseMap: 'hoặc chạm bản đồ',
    sheetDismiss: 'Để sau',
    // Status panels
    loadingLabels: [
      'Đang xem gần bạn có gì đang mở',
      'Đang cân thời gian và túi tiền',
      'Đang xếp thứ tự các chỗ dừng',
      'Vẫn đang tính — bộ tối ưu đang làm kỹ',
    ],
    emptyTitle: 'Chưa có gì vừa — tiếc ghê',
    emptyBody: 'Ngân sách của bạn hơi sít sao cho khu này.',
    addTime: '+30 phút',
    addMoney: '+100.000 ₫',
    errorTitle: 'Không kết nối được với máy chủ',
    errorBody: 'Kiểm tra mạng rồi thử lại nhé.',
    retry: 'Thử lại',
    errorDetails: 'Chi tiết kỹ thuật',
    // Results
    resultsTitle: 'Lịch trình của bạn',
    ride: (min) => `đi ${min} phút`,
    stay: (min) => `ở lại ${min} phút`,
    openInMaps: (name) => `Mở ${name} trong Google Maps`,
    free: 'miễn phí',
    stopWord: () => 'chỗ',
    withinBudget: 'trong ngân sách',
    startOver: 'Làm lại',
    // Map + announcements
    mapHint: 'Chạm bản đồ để chọn điểm bắt đầu',
    annPlanning: 'Đang lên lịch trình',
    annError: 'Không kết nối được với máy chủ',
    annEmpty: 'Không có lịch trình nào vừa ngân sách',
    annStops: (n) => `${n} chỗ dừng`,
  },
}
