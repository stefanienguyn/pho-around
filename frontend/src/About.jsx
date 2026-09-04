import { useEffect, useState } from 'react'
import {
  AirplaneTiltIcon,
  ArrowRightIcon,
  ForkKnifeIcon,
  GithubLogoIcon,
  HeartIcon,
  LinkedinLogoIcon,
  MapPinIcon,
} from '@phosphor-icons/react'
import { getInitialLang, persistLang } from './i18n'
import './App.css'

// Placeholder — swap in the real support/donation link when it exists.
// '#' keeps the element a genuine link (focusable, styled) without going
// anywhere yet.
const SUPPORT_URL = '#'

// Team profile links — paste the real URLs over the '#' placeholders.
const PHUONG_LINKEDIN = 'https://www.linkedin.com/in/stef-nguyen'
const PHUONG_GITHUB = "https://github.com/stefanienguyn"
const DUC_LINKEDIN = 'https://github.com/duongduc388222'
const DUC_GITHUB = 'https://www.linkedin.com/in/duchduong/'

// Every visible string on the page, both languages, one place. The title
// is split around the highlighted word so the <mark> can wrap just it.
const STRINGS = {
  en: {
    docTitle: 'About us — Phở around',
    navPlanner: 'Planner',
    navAbout: 'About Us',
    navCta: 'Plan a Trip',
    badge: 'EST. 2026 • Global nomads',
    titlePre: 'We’re ',
    titleMark: 'Saigonese',
    titlePost: ' who',
    titleLine2: 'go out a lot.',
    titleAside: '(maybe a little too much?)',
    lead: 'Phở around was born with the desire to spread the lively life at Sài Gòn. We hope to help you find an interesting spot in the city.',
    storyAlt: 'Hand-drawn selfie of the Phở around friends',
    storyLabel: 'Our story',
    storyH2: 'It started with some friends who love to wander.',
    storyP1:
      'It all started with the love we have for our city, Sài Gòn or Ho Chi Minh City, Vietnam. We want to introduce the places that we go, love, and enjoy to everyone. This is a way that we want to appreciate the city, the people, and all of our hangouts.',
    storyP2:
      "If you don't know where to go, need new places to explore. Let us take you around! Everything as of now is a demo and being tested. We're all college students trying to learn things, so we appreciate your patience and time to try this web out!",
    support: 'Support our journey',
    statsLabel: 'Phở around in numbers',
    stats: ['Countries Tasted', 'Noodle Enthusiasts', 'Secret Food Spots', 'Empty Stomachs'],
    teamLabel: 'The team',
    teamH2: 'Meet the Folks',
    teamSub: 'The humans (and hungry eaters) behind your next adventure.',
    ctaLabel: 'Plan a trip',
    ctaH2: 'Ready to start slurping?',
    ctaText:
      "Tell us where you're starting, how much time you have, and your budget — we'll map out the rest.",
    ctaButton: 'Plan a Trip',
  },
  vi: {
    docTitle: 'Về tụi mình — Phở around',
    navPlanner: 'Lên lịch trình',
    navAbout: 'Về tụi mình',
    navCta: 'Lên kèo ngay',
    badge: 'Từ 2026 • Hội mê chơi',
    titlePre: 'Người',
    titleMark: 'Sài Gòn',
    titlePost: ' và',
    titleLine2: 'ham chơi.',
    titleAside: '(hơi nhiều tí?)',
    lead: 'Phở around ra đời từ việc muốn truyền tải sự nhộn nhịp của Sài Gòn. Tụi mình mong rằng sẽ giúp mọi người thấy được một góc khác của thành phố này.',
    storyAlt: 'Bức vẽ cả nhóm Phở around tự chụp',
    storyLabel: 'Chuyện của tụi mình',
    storyH2: 'Mọi chuyện bắt đầu với một nhóm bạn ham chơi.',
    storyP1:
      'Mọi thứ bắt đầu với tình yêu tụi mình dành cho Sài Gòn. Tụi mình muốn giới thiệu tất cả những nơi bọn mình đã đi, yêu thích, và muốn gửi đến cho mọi người. Đây là một dự án nhỏ để tụi mình (những người đi du học hoặc iu Sài Gòn) nhớ về thành phố nơi tụi mình sinh ra và lớn lên, và tất cả những cuộc đi chơi tụi mình có.',
    storyP2:
      'Nếu mọi người không biết đi đâu với nhóm bạn của mình, hoặc muốn tìm những chỗ đi chơi mới. Hãy để tụi mình giúp mọi người nhé! Hiện tại chỉ đang là demo và tụi mình đang rất cố gắng để hoàn thiện. Vì chỉ là những sinh viên đang học hỏi, nên tụi mình cảm ơn mọi người vì đã chiếu cố và cho chiếc web này 1 cơ hội.',
    support: 'Ủng hộ hành trình của tụi mình',
    statsLabel: 'Phở around qua những con số',
    stats: ['Quốc gia đã nếm', 'Tín đồ sợi phở', 'Điểm ăn bí mật', 'Bụng đói ra về'],
    teamLabel: 'Đội ngũ',
    teamH2: 'Gặp hội mê chơi',
    teamSub: 'Những con người (ham chơi) đứng sau chuyến đi sắp tới của bạn.',
    ctaLabel: 'Lên lịch trình',
    ctaH2: 'Sẵn sàng đi chưa?',
    ctaText:
      'Cho tụi mình biết bạn bắt đầu từ đâu, có bao nhiêu thời gian và ngân sách — phần còn lại để tụi mình lo nhé!',
    ctaButton: 'Lên lịch trình ngay',
  },
}

// Stats band values are language-neutral; the labels live in STRINGS.
const STAT_VALUES = ['10+', '100+', '500', '0']

// One entry per team card. `tone` picks the avatar's fill (a .tone-* class);
// `icons` are the two social glyphs the design shows — decorative here, since
// there are no real profiles to link to yet. Roles and bios carry both
// languages inline so a card stays one self-contained record.
const TEAM = [
  {
    initial: 'M',
    tone: 'green',
    name: 'Phương',
    photo: '/fuong.PNG',
    role: { en: 'Founder', vi: 'Sáng lập' },
    bio: {
      en: 'Started Phở-around after being homesick when study abroad. Believes everyone should try nước mía.',
      vi: 'Lập ra Phở-around vì nhớ nhà khi đi du học. Tin rằng mọi người nên thử nước mía.',
    },
    links: [
      { Icon: LinkedinLogoIcon, href: PHUONG_LINKEDIN, label: 'LinkedIn' },
      { Icon: GithubLogoIcon, href: PHUONG_GITHUB, label: 'GitHub' },
    ],
  },
  {
    initial: 'S',
    tone: 'yellow',
    name: 'Đức',
    photo: '/duc.PNG',
    role: { en: 'Chief Food Officer', vi: 'Giám đốc ẩm thực' },
    bio: {
      en: 'Ate countless bowls of bún mắm. He ensures the group never get hungry.',
      vi: 'Đã ăn rất nhiều bún mắm. Đảm bảo rằng bạn không bao giờ đói bụng.',
    },
    links: [
      { Icon: LinkedinLogoIcon, href: DUC_LINKEDIN, label: 'LinkedIn' },
      { Icon: GithubLogoIcon, href: DUC_GITHUB, label: 'GitHub' },
    ],
  },
  {
    initial: 'A',
    tone: 'blue',
    name: 'Uyên',
    photo: '/ku.PNG',
    role: { en: 'Lead Discount Director', vi: 'Hội trưởng hội giảm giá' },
    bio: {
      en: 'Make sure you have the best deal and pay the least money wherever you go.',
      vi: 'Luôn đảm bảo bạn có mã khuyến mãi lời nhất và phải chi số tiền ít nhất',
    },
    links: [], // icons parked until Uyên picks her profiles
  },
  {
    initial: 'E',
    tone: 'lilac',
    name: 'Toàn',
    photo: '/toan.PNG',
    role: { en: 'Scooter Spotify', vi: 'Người hát rong' },
    bio: {
      en: 'Choose your favorite song and he makes sure you have a concert on the go (especially Hiếu Thứ Hai).',
      vi: 'Chọn một bài nhạc bạn thích và tận hưởng concert trên đường (đặc biệt là Hiếu Thứ Hai).',
    },
    links: [], // icons parked until Toàn picks his profiles
  },
]

/**
 * One team card: avatar disc, role eyebrow, name, bio, profile links.
 * `person` is one TEAM entry; `lang` picks the role/bio language.
 */
function TeamCard({ person, lang }) {
  return (
    <li className="about-card">
      {/* Photo when there is one, initial-on-color otherwise. The tone
          still paints the ring area behind a transparent photo edge. */}
      <span className={`about-avatar tone-${person.tone}`} aria-hidden="true">
        {person.photo ? <img src={person.photo} alt="" /> : person.initial}
      </span>
      <p className="about-eyebrow about-role">{person.role[lang]}</p>
      <h3 className="about-name">{person.name}</h3>
      <p className="about-bio">{person.bio[lang]}</p>
      {person.links.length > 0 && (
        <span className="about-socials">
          {person.links.map(({ Icon, href, label }) => (
            <a key={label} href={href} aria-label={`${person.name} — ${label}`}>
              <Icon size={24} />
            </a>
          ))}
        </span>
      )}
    </li>
  )
}

/**
 * The About Us page (Figma node 1:2): nav, highlighted hero headline, story,
 * stats band, team grid, newsletter CTA. (The design's ink footer is parked
 * for now — restore it from the Figma when wanted.) Static marketing content;
 * the nav and CTAs link back to the planner at "/".
 *
 * Bilingual: `lang` selects a branch of STRINGS. It starts from the saved
 * choice or the browser language, and the EN/VI toggle stores an override.
 */
function About() {
  const [lang, setLang] = useState(getInitialLang)
  const t = STRINGS[lang]

  function switchLang(next) {
    setLang(next)
    persistLang(next)
  }

  // The tab title and the document's declared language follow the toggle
  // (screen readers pick their voice from <html lang>). Restored on
  // unmount: the planner is English-labelled with Vietnamese content.
  useEffect(() => {
    document.title = t.docTitle
    document.documentElement.lang = lang
    return () => {
      document.title = 'Phở around'
      document.documentElement.lang = 'en'
    }
  }, [lang, t.docTitle])

  return (
    <div className="about">
      <nav className="about-nav" aria-label="Main">
        <a className="about-brand" href="/">
          {/* Same asset as the tab icon and the planner's nav — already
              cached. Empty alt: the link's own text names the brand. */}
          <img className="about-logo-img" src="/favicon.png" alt="" />
          Phở around
        </a>
        <div className="about-nav-links">
          <a className="about-nav-link" href="/">
            {t.navPlanner}
          </a>
          <a className="about-nav-link is-current" href="/about" aria-current="page">
            {t.navAbout}
          </a>
        </div>
        <div className="about-nav-right">
          <div className="lang-toggle" role="group" aria-label="Language / Ngôn ngữ">
            <button
              type="button"
              className={lang === 'en' ? 'is-on' : ''}
              aria-pressed={lang === 'en'}
              onClick={() => switchLang('en')}
            >
              EN
            </button>
            <button
              type="button"
              className={lang === 'vi' ? 'is-on' : ''}
              aria-pressed={lang === 'vi'}
              onClick={() => switchLang('vi')}
            >
              VI
            </button>
          </div>
          <a className="about-cta-button" href="/">
            {t.navCta}
          </a>
        </div>
      </nav>

      <header className="about-hero">
        <p className="about-eyebrow about-badge">{t.badge}</p>
        <h1 className="about-title">
          {t.titlePre}
          <mark className="about-highlight">{t.titleMark}</mark>
          {t.titlePost}
          <br />
          {t.titleLine2}
        </h1>
        <p className="about-title-aside">{t.titleAside}</p>
        <p className="about-lead">{t.lead}</p>
      </header>

      <section className="about-shell about-story" aria-label={t.storyLabel}>
        <div className="about-story-art">
          <div className="about-story-frame">
            <img className="about-story-photo" src="/loppy.png" alt={t.storyAlt} />
          </div>
          <span className="about-sticker at-top" aria-hidden="true">
            <AirplaneTiltIcon size={30} weight="bold" />
          </span>
          <span className="about-sticker at-bottom" aria-hidden="true">
            <HeartIcon size={30} weight="bold" />
          </span>
        </div>
        <div>
          <h2 className="about-h2">{t.storyH2}</h2>
          <p className="about-story-text">{t.storyP1}</p>
          <p className="about-story-text">{t.storyP2}</p>
          <a className="about-support" href={SUPPORT_URL}>
            {t.support} <ArrowRightIcon size={20} weight="bold" aria-hidden="true" />
          </a>
        </div>
      </section>

      <section className="about-stats-band" aria-label={t.statsLabel}>
        <ul className="about-shell about-stats">
          {STAT_VALUES.map((value, i) => (
            <li key={t.stats[i]}>
              <p className="about-stat-value">{value}</p>
              <p className="about-eyebrow about-stat-label">{t.stats[i]}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="about-shell about-team" aria-label={t.teamLabel}>
        <h2 className="about-h2">{t.teamH2}</h2>
        <p className="about-team-sub">{t.teamSub}</p>
        <ul className="about-team-grid">
          {TEAM.map((person) => (
            <TeamCard key={person.name} person={person} lang={lang} />
          ))}
        </ul>
      </section>

      <section className="about-shell about-cta-section" aria-label={t.ctaLabel}>
        <div className="about-banner">
          <span className="about-banner-decor at-top" aria-hidden="true">
            <MapPinIcon size={120} weight="fill" />
          </span>
          <span className="about-banner-decor at-bottom" aria-hidden="true">
            <ForkKnifeIcon size={120} weight="fill" />
          </span>
          <h2 className="about-banner-title">{t.ctaH2}</h2>
          <p className="about-banner-text">{t.ctaText}</p>
          <a className="about-cta-button about-banner-cta" href="/">
            {t.ctaButton}
          </a>
        </div>
      </section>
    </div>
  )
}

export default About
