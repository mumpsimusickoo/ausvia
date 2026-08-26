// AUSVIA Tailwind config. Ported verbatim from the inline tailwind.config
// block that used to live in app/templates/base.html (Tailwind build pass,
// 2026-08-26 - replaces the CDN runtime). No token values changed in this
// move - see DECISIONS.md for why (CDN -> committed build, not a redesign).
//
// content: every directory that can contain a Jinja template with class
// names, scanned as plain text (Tailwind's scanner doesn't parse Jinja,
// it just regexes for class-shaped tokens - which is exactly why it's
// safe here: this app was audited before this pass for any class name
// built dynamically in Python or via Jinja string-concatenation, and none
// were found - see DECISIONS.md. Every status/semantic -> class mapping
// in this app is a complete-literal {% if/elif/else %} branch, so every
// class that can ever render is a real substring of a scanned .html file.
module.exports = {
  content: [
    './app/templates/**/*.html',
  ],
  theme: {
    extend: {
      fontFamily: {
        // Body/UI face - replaces Inter (removed from the <link> in
        // base.html; nothing references it anymore).
        sans: ['"IBM Plex Sans"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        // Titles, section headings, values, numbers only - never body
        // text. Supersedes the old "Sora is wordmark-only" decision;
        // see DECISIONS.md for the loading-cost consequence.
        display: ['Sora', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        // Labels and source attributions only - never body copy.
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      fontSize: {
        display: ['52px', { lineHeight: '1.04', letterSpacing: '-0.035em' }],
        title: ['28px', { lineHeight: '1.2' }],
        section: ['19px', { lineHeight: '1.35' }],
        body: ['15px', { lineHeight: '1.62' }],
        label: ['11px', { lineHeight: '1.4', letterSpacing: '0.1em' }],
      },
      borderRadius: {
        // The bundle's 20px "panel" radius - no exact Tailwind default
        // (2xl=16px, 3xl=24px). Available; no panel component exists
        // yet, so nothing consumes this today.
        panel: '20px',
      },
      boxShadow: {
        // Exact bundle values, for when hairline/overlay precision
        // actually matters. The existing `shadow-sm` (used at many call
        // sites already) is close enough to `hairline` that it wasn't
        // worth a mass rename - see DESIGN_SYSTEM.md.
        hairline: '0 1px 2px rgba(12,16,19,.05)',
        overlay: '0 12px 32px -10px rgba(12,16,19,.18)',
        // Ink-surface overlay shadow (the bundle's dark --sh2 - a
        // stronger, near-black shadow since a hairline shadow doesn't
        // read against a dark background). The bundle's dark --sh is
        // literally `none` - no ink-surface hairline token exists on
        // purpose, not an omission.
        'ink-overlay': '0 16px 40px -12px rgba(0,0,0,.6)',
      },
      colors: {
        // Theme-following roles - each resolves to a CSS custom
        // property that swaps under :root[data-theme="dark"] (defined
        // in assets/css/input.css). Class names are unchanged from the
        // original foundation-tokens pass; only the value source
        // changed, from a static hex literal to var(--x). See
        // DESIGN_SYSTEM.md "Theme architecture - 2026-08-25 pass" for
        // which surfaces this applies to and which stay fixed (below).
        card: 'var(--card)',       // see note below
        raised: 'var(--raised)',
        line: 'var(--line)',
        line2: 'var(--line2)',
        t1: 'var(--t1)',
        t2: 'var(--t2)',
        t3: 'var(--t3)',
        brand: 'var(--brand)',
        'brand-hover': 'var(--brand-hover)',
        tint: 'var(--tint)',
        tint2: 'var(--tint2)',
        paper: 'var(--page)',      // page background (Porzellan/Tinte)
        ok: 'var(--ok)', 'ok-tint': 'var(--ok-tint)',
        warn: 'var(--warn)', 'warn-tint': 'var(--warn-tint)',
        err: 'var(--err)', 'err-tint': 'var(--err-tint)',
        info: 'var(--info)', 'info-tint': 'var(--info-tint)',
        // Text/icon color for content sitting on a filled brand or
        // semantic surface (see input.css's --on-fill definition for
        // the measured reasoning).
        'on-fill': 'var(--on-fill)',
        // `card` didn't exist before the theme pass - the light value
        // (#FFFFFF) was just Tailwind's built-in `white`, used directly
        // everywhere a panel needed a light background. That stops
        // working once dark mode exists: `white` itself must stay a
        // literal, fixed color (it's also used for on-ink text and
        // white/NN overlays on the surfaces that stay fixed below, and
        // redirecting the built-in would have silently broken those).
        // `card` is the theme-aware name for "elevated panel background".

        // Fixed palette - deliberately NOT var()-based, unaffected by
        // the theme toggle. Used only by surfaces confirmed (against the
        // bundle directly, not assumed) to stay ink regardless of theme:
        // the mobile topbar/drawer, the landing hero (no bundle
        // equivalent exists to model a themed version on - see
        // DESIGN_SYSTEM.md), and the bg-ink/20 divider trick in the
        // application-detail station tracker (a fixed-black-at-opacity
        // effect, not a themed surface).
        ink: '#0C1013',
        'ink-card': '#12171B',
        'ink-raised': '#171E23',
        'ink-line': '#222A30',
        'ink-line2': '#303B42',
        'ink-t1': '#E9EFF1',
        'ink-t2': '#9DABB3',     // mobile topbar/drawer nav text
        'ink-t3': '#6E7C85',     // NOT used anywhere - fails AA at normal text size, see DESIGN_SYSTEM.md
        'ink-tint': '#0E2327', 'ink-tint2': '#123337',
        'ink-ok': '#4BBE7E', 'ink-ok-tint': '#0F2419',
        'ink-warn': '#D9A22B', 'ink-warn-tint': '#241C0B',
        'ink-err': '#E4665A', 'ink-err-tint': '#251311',
        'ink-info': '#5FA6D6', 'ink-info-tint': '#0E1D26',
        // Accent text/icon on ink (mobile topbar/drawer nav-active,
        // landing hero badge, logo symbol on the surfaces above).
        bright: '#4FC3C9',
        // Primary action FILL specifically on the fixed-ink landing
        // hero. Distinct from `bright` (a text/icon accent).
        'bright-action': '#12949B',
        'bright-action-hover': '#3FBFC4',
        // The light backing behind the landing hero's counterform
        // cutout (see landing.html) - a pinned copy of the exact hex
        // `paper` held before the theme pass, not a live reference to
        // it, since `paper` now varies by theme and this must not.
        // Single consumer today.
        'hero-backing': '#F2F5F6',
      },
    },
  },
}
