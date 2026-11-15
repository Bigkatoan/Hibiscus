# Accessibility checklist — WCAG 2.1 AA, tailored to Hibiscus

Target: WCAG 2.1 level AA (PLAN §6). Automated: axe-core in Playwright on every main route
(ADR-0007, A6/A10). Manual: the checks marked **M** below, done by A7 in the Phase-4 UAT
walkthrough with keyboard only, 200 % zoom, NVDA + Firefox and VoiceOver + Safari spot checks.
Each item names the WCAG success criterion (SC) and the screens (S-xx, `wireframes.md`) where it
bites hardest.

## A. Global (every screen)

| # | Check | SC | How to verify |
|---|---|---|---|
| A1 | `<html lang="vi">` / `lang="en"` follows the UI language; English log/technical blocks inside a vi page carry `lang="en"` | 3.1.1, 3.1.2 | inspect DOM after language switch |
| A2 | Skip link "Skip to main content" is the first focusable element and visible on focus | 2.4.1 | **M** Tab once on each page |
| A3 | Unique `<title>`: "<page> · <workspace> · Hibiscus" | 2.4.2 | axe + manual |
| A4 | Landmarks: one `<main>`, `<nav aria-label={common.nav.main}>`, breadcrumb `<nav aria-label={common.nav.breadcrumb}>` | 1.3.1 | axe |
| A5 | Heading order h1 (page) → h2 (sections/cards) → h3, no skipped levels | 1.3.1, 2.4.6 | **M** heading list in screen reader |
| A6 | Visible focus indicator, ≥ 3:1 against adjacent colours, never removed (`outline: none` banned without replacement) | 2.4.7, 1.4.11 | **M** keyboard pass |
| A7 | Focus order follows visual order; dialogs trap focus and return it to the trigger on close (Radix default — do not override) | 2.4.3 | **M** |
| A8 | Text contrast ≥ 4.5:1 (≥ 3:1 for ≥ 24px/19px bold) in light **and** dark theme, including placeholder, disabled-but-informative text, chart labels | 1.4.3 | axe + contrast checker on tokens |
| A9 | UI components and graphical objects (inputs, toggles, chart lines, progress bars) ≥ 3:1 | 1.4.11 | token check |
| A10 | Status never by colour alone: every status badge = icon + text (`runs.status.*`, `version_status.*`, verified ✔/✖ + word) | 1.4.1 | **M** greyscale screenshot |
| A11 | Reflow at 320 CSS px (400 % zoom) without horizontal scroll, except data tables and charts which scroll inside their own container with a visible scrollbar | 1.4.10 | **M** 1280px window at 400 % |
| A12 | Text spacing override (line-height 1.5, letter 0.12em) does not clip text — Vietnamese diacritics need line-height ≥ 1.4 by default | 1.4.12 | bookmarklet |
| A13 | 200 % text resize: no truncated buttons; vi strings (longer) wrap | 1.4.4 | **M** |
| A14 | All functionality by keyboard; no keyboard trap; custom shortcuts (episode ←/→, space) only active when the viewer has focus and documented in a visually hidden hint | 2.1.1, 2.1.2, 2.1.4 | **M** |
| A15 | Pointer targets ≥ 24×24 px (aim 44×44 on phone) for icon buttons (copy, revoke, ⋯, bell) | 2.5.5 (AAA, adopted as goal) | visual |
| A16 | Every icon-only button has an accessible name from i18n (`aria-label={t(...)}`), e.g. bell `notifications.open` + unread count | 4.1.2 | axe |
| A17 | Live regions: one polite region for status changes (`common.a11y.live_region_status`), one assertive region for errors only. Do **not** announce SSE heartbeats, metric ticks or progress every second (announce at most every 10 % or on status change) | 4.1.3 | **M** NVDA during a live run |
| A18 | No content flashes > 3 times/s (log follow and charts update smoothly; no blinking "live" dot — use a static dot + text) | 2.3.1 | visual |
| A19 | Session timeout: access token refresh is silent; if re-login is needed, form data in the wizard is preserved (F3.6) | 2.2.1 | **M** expire cookie mid-wizard |
| A20 | `prefers-reduced-motion`: disable chart animations and progress shimmer | 2.3.3 (AAA, adopted) | OS setting |
| A21 | Error pages and toasts include a text request id that can be selected and copied | 3.3.3 | **M** |

## B. Forms (auth, invites, tokens, upload, wizard, admin)

| # | Check | SC | Screens |
|---|---|---|---|
| B1 | Every input has a visible `<label>` (placeholders are examples only) | 1.3.1, 3.3.2 | all |
| B2 | Required fields marked with text "(required)" via `common.a11y.required_field`, not only `*` | 3.3.2 | S-02, S-08, S-10 |
| B3 | Errors: `aria-invalid="true"`, message linked with `aria-describedby`, text says how to fix (`errors.field.*`) | 3.3.1, 3.3.3 | all |
| B4 | On submit with errors: focus moves to an error summary (`errors.general.field_summary_*`) whose items link to the fields | 3.3.1 | S-10 settings, S-02 |
| B5 | `autocomplete` tokens: `email`, `current-password`, `new-password`, `one-time-code`, `name` | 1.3.5 | S-01, S-01b, S-02, S-05, account |
| B6 | Password fields allow paste and password managers; show/hide toggle has a name and `aria-pressed` | 3.3.8 (2.2) adopted | S-01, S-02 |
| B7 | OTP input is one `<input inputmode="numeric" autocomplete="one-time-code">`, not 6 separate boxes (screen readers, paste) | 1.3.5, 2.1.1 | S-01b, S-04 |
| B8 | Turnstile widget: if it fails, the text alternative explains and offers retry; never the only way to proceed without explanation | 1.1.1, 3.3.1 | S-01, S-05 |
| B9 | Destructive/irreversible submissions (revoke token, delete dataset, cancel run, disable user) require a confirm step that states consequences | 3.3.4 | S-09, S-07, S-12, S-17 |
| B10 | Schema-driven policy fields: label from `policy.*.label`, `help` as description (`aria-describedby`), default value and "changed" state exposed as text, number inputs keep `min`/`max` from schema | 1.3.1, 3.3.2 | S-10 |
| B11 | Policy cards and preset choices are a real `radiogroup` (arrow keys), disabled cards have `aria-disabled` + reason text reachable by keyboard | 4.1.2 | S-10 |
| B12 | Held-out slider has a numeric input alternative and announces "10 % (2 episodes)" | 1.1.1, 4.1.2 | S-10 |
| B13 | Wizard step indicator is a list with `aria-current="step"`; step change moves focus to the step heading | 1.3.1, 2.4.3 | S-10 |
| B14 | File drop zone is also a native file `<input>` reachable by keyboard, with the accepted formats as text | 2.1.1 | S-06 |

## C. Live data, charts and media

| # | Check | SC | Screens |
|---|---|---|---|
| C1 | Upload/hash progress uses `role="progressbar"` with `aria-valuenow`, label and value text (`common.a11y.progress`) | 4.1.2 | S-06, S-12 |
| C2 | Every chart has a text summary (`common.a11y.chart_summary`) and a "Show data as table" toggle rendering the same (downsampled) points as an HTML table | 1.1.1, 1.3.1 | S-12 metrics, S-13, S-07b, eval plots |
| C3 | Multi-series charts distinguish series by dash pattern/marker **and** colour; legend items are toggle buttons with names | 1.4.1 | S-13, S-07b |
| C4 | Canvas charts are `aria-hidden` with the summary/table as the accessible alternative (canvas itself is not navigable) | 1.1.1 | charts |
| C5 | Eval plots (PNG from bundle) have alt text `eval.plot_alt` and the per-joint table next to them | 1.1.1 | S-12 eval, S-15 |
| C6 | Dataset videos have no audio; provide a text description (episode index, task, duration) as the accessible name; controls are keyboard operable; no autoplay with sound | 1.2.1 (N/A audio), 2.2.2 | S-07b |
| C7 | Video autoplay muted is allowed only when the user opened the episode; pause/stop available | 2.2.2 | S-07b |
| C8 | Log viewer: monospace `<pre>` with `lang="en"`, "Follow new lines" toggle off when the user scrolls up or focuses inside; search results announced as count | 2.2.2, 4.1.3 | S-12 log |
| C9 | SSE connection state is shown as text ("Live" / "Connection lost, reconnecting…"), announced once per change | 4.1.3 | S-12 |
| C10 | Auto-updating lists (runs, queue) don't move focus or re-order under the user's focus; new rows are announced politely | 2.2.2, 3.2.2 | S-11, S-16 |
| C11 | QR code for TOTP has the setup key as text alternative right below it | 1.1.1 | S-04 |

## D. Tables and dense admin views

| # | Check | SC |
|---|---|---|
| D1 | Data tables use `<table>` with `<th scope>` and a caption (visually hidden allowed) | 1.3.1 |
| D2 | Sortable headers are buttons with `aria-sort` and `common.a11y.sorted_by` | 4.1.2 |
| D3 | Row actions in a "⋯" menu are a Radix menu with the row's name in the trigger label ("Actions for Linh") | 2.4.6, 4.1.2 |
| D4 | On phone width, tables switch to stacked cards with label/value pairs (`<dl>`) | 1.4.10 |
| D5 | Audit log time column uses `<time datetime>` with absolute time available | 1.3.1 |

## E. Content

| # | Check | SC |
|---|---|---|
| E1 | Instructions do not rely on shape/position only ("click the green button") | 1.3.3 |
| E2 | Link text is meaningful out of context ("Open model so101_…", not "here") | 2.4.4 |
| E3 | Consistent naming of the same function across pages (glossary, `copy-deck.md` §2) | 3.2.4 |
| E4 | External links (Hugging Face, user guide) say so (`common.a11y.external_link`) | 3.2.5 (AAA, adopted) |
| E5 | Language switcher entries use the language's own name and their own `lang` attribute | 3.1.2 |

## F. Test procedure (A7 Phase 4, A10 automation)

1. `pnpm exec playwright test` with `@axe-core/playwright` on: sign in, 2FA, register-invite,
   overview, datasets list, upload, dataset detail (validation with warnings), episode viewer,
   wizard each step, run detail (running fixture + failed fixture), compare, models list, model
   detail, queue, members, tokens, admin users/audit/system — in **vi and en**, light and dark.
   Zero violations of impact `serious`/`critical`.
2. Keyboard-only walkthrough of F0 browser path (UAT-05..UAT-12 in `uat.md`).
3. NVDA + Firefox: sign in with 2FA, run wizard, listen to a live run for 2 minutes (A17).
4. 400 % zoom on S-10 and S-12; 320 px phone emulation on S-06, S-12, S-15.
5. Record results in `docs/qa/` (A10) with screenshots; blockers filed against A6.
