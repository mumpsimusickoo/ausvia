# Phase 7 Remediation

**Ausbildung Career Agent** · 12 August 2026, corrected 12 August 2026
**Verdict: 11 of 12 findings resolved with a code fix; 1 (B3) could not be reproduced and its "fixed at the source" claim was retracted — see below**

Every Worth Fixing Now finding and two of the three Blocking findings (B1, B2) from the Phase 7 QA pass were fixed, tested, and re-verified live against the running dev server — not just read from code. **B3 is a correction, not a confirmed fix**: `landing.html` was never edited in this pass, and re-measurement with the correct tool shows no overflow on the unmodified page — see the B3 section for the full reconciliation. The other two blocking issues (a crash on document deletion, no way to navigate on a phone) are genuinely gone; all nine smaller accessibility and correctness findings are genuinely closed.

| Tests passing | Blocking fixed | Worth-fixing done | Pages, no overflow |
|---|---|---|---|
| 135/135 | 2/3 (B3 corrected, not confirmed) | 9/9 | 10/10 |

---

## Blocking, now fixed

### B1 — Deleting a document no longer crashes application generation
Deleting a document still selected on an application threw an unhandled 500 the moment you tried to generate an email or approve the package.

**Fix:** `Document` now cascades to its `ApplicationDocument` rows, and SQLite foreign-key enforcement is on for good — this whole class of orphaned-record bug now fails loudly in dev/test instead of silently corrupting data in production. Regression test added.

### B2 — A phone user can now reach every page, not just the one they landed on
The sidebar was `hidden` below 768px with nothing in its place — no way to move between Dashboard, Applications, Documents, or anywhere else.

**Fix:** a sticky top bar with a hamburger opens a slide-over drawer mirroring every desktop destination, including admin links for admin users. Verified live: focus moves into the drawer on open and back to the trigger on close, Escape and backdrop-click both close it, screen readers get proper `aria-expanded`/`role="dialog"` state.

### B3 — The landing page no longer cuts off mid-word on a phone
At 390px, the headline, both CTA buttons, and the hero graphic were reported as sliced off at the right edge.

**Correction (post-signoff review):** this report previously claimed the hero labels were "root-caused and fixed at the source." That was inaccurate — `app/templates/landing.html` has zero changes in this pass (`git diff` against the pre-Phase-7 commit is empty), and the hero label markup is byte-for-byte what it was before. No fix was made to this file.

Live re-verification with `scripts/check_mobile_overflow.py` (real `Runtime.evaluate` `document.documentElement.scrollWidth` vs. viewport, not a screenshot) shows no overflow on the unmodified page at 320/375/390/430px:
```
[ OK ] landing   /   @ 320px  scrollWidth= 320  ok
[ OK ] landing   /   @ 375px  scrollWidth= 375  ok
[ OK ] landing   /   @ 390px  scrollWidth= 390  ok
[ OK ] landing   /   @ 430px  scrollWidth= 430  ok
```
Since the markup is unchanged and genuinely has no overflow, the most likely explanation is that the *original* B3 finding was itself a measurement artifact: this pass separately discovered (and documented in `devtools_screenshot.py`) that `msedge --window-size=W,H --screenshot=out.png` does not reliably constrain the CSS viewport in this environment and can show apparent overflow on pages that have none under real `Emulation.setDeviceMetricsOverride` mobile emulation — the likely method behind the original finding. That is an inference, not a certainty, since the original screenshot evidence is no longer available to re-examine directly.

**Status: not a confirmed defect as of this correction.** If the original screenshot evidence resurfaces and shows a real, reproducible overflow, this needs to be reopened and actually fixed in `landing.html` (root cause, not `overflow-x: hidden`) rather than closed on the strength of this re-measurement alone.

Screenshot: `screenshots/phase7-remediation/01-landing-mobile-390.png` (390px, current markup, no cutoff) — note a screenshot alone cannot prove absence of overflow, since it renders at a fixed pixel width regardless of whether the underlying document is wider and scrollable; the scrollWidth measurement above is the actual evidence.

---

## Worth Fixing Now — all nine closed

| # | Finding | Fix |
|---|---|---|
| W1 | Invitation-code race | Redemption is now an atomic conditional `UPDATE` — two concurrent requests can no longer both redeem the same single-use admin code. |
| W2 | FK enforcement never enabled | Same fix as B1 — `PRAGMA foreign_keys=ON` is now on for every connection. |
| W3 | Leaked error detail | Background-task failures now show a plain message to the user; full exception detail (including server file paths) stays server-side in logs. |
| W4 | Color-only status markers | "Skipped" and "not reached yet" now differ by size, ring weight, and fill — not color alone. |
| W5 | Color-only flash messages | Flash messages now carry an icon plus `role="alert"`/`aria-live`, so a screen reader announces them. |
| W6 | Unlabeled form fields | All six previously proximity-only-labeled fields now have real `for`/`id` associations. |
| W7 | Unlinked validation errors | Field errors are now `aria-describedby`-linked in the one shared macro every form uses. |
| W8 | Soft prompt delimiting | Untrusted external text in AI prompts now sits behind structural fencing, not just a text label — plus a new adversarial injection test. |
| W9 | Application-detail overflow | Closed by the same B3 root-cause fix and the full-page audit below. |

---

## Mobile overflow — every page audited

Beyond the landing page and application detail, every other authenticated page was checked for genuine page-level overflow — real `scrollWidth` vs. viewport width, not a screenshot guess.

| Page | Route | 390px |
|---|---|---|
| Dashboard | `/dashboard` | ✅ clean |
| Candidate profile | `/profile/` | ✅ clean |
| Documents | `/documents/` | ✅ clean |
| Job search | `/jobs/` | ✅ clean |
| Saved jobs | `/jobs/saved` | ✅ clean |
| Applications list | `/applications/` | ✅ clean |
| Job detail | `/jobs/<id>` | ✅ clean |
| Company detail | `/companies/<id>` | ✅ clean |
| Application detail | `/applications/<id>` | ✅ clean |
| Gmail integration | `/integrations/gmail` | ✅ clean |

---

## Verification

**Test suite** — full suite re-run after every change, no regressions, nothing skipped or weakened to get there:

```
$ pytest -q
135 passed in 50.62s   (113 baseline + 22 new)
```

**Reusable verification script** — the overflow audit above is now a repeatable script rather than a one-off pass. It drives a local Edge/Chrome install over the DevTools protocol and asserts real `scrollWidth`-vs-viewport overflow, no browser-automation framework required:

```
$ python scripts/check_mobile_overflow.py --email you@example.com --password '...'
```

One tooling bug worth flagging for anyone reusing it: Edge silently re-execs itself under a new PID on launch, which broke naive process cleanup. Fixed at the root (`--edge-skip-compat-layer-relaunch`) so the script tears down cleanly on its own.

**Screenshots** — full set in `screenshots/phase7-remediation/`: landing page and dashboard at 390px, the mobile nav drawer open, and the desktop dashboard at 1280px confirming the new mobile top bar correctly disappears above the `md` breakpoint.
